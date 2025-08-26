import numba as nb
import numpy as np
import pandas as pd 

from numba.experimental import jitclass

from functools import lru_cache
import math

from skimage.transform import resize

from ifcb.data.adc import SCHEMA_VERSION_1
from ifcb.data.stitching import InfilledImages

# numba implementation of bin packing algorithm

DOESNT_FIT = -9999999
NO_SECTION = -1

X = 0
Y = 1
W = 2
H = 3
DELETION_FLAG = 4

DELETED = 0
NOT_DELETED = 1


@nb.jit(nopython=True)
def intersects(x, y, w, h, xx, yy, ww, hh):
    self_left, self_right = x, x + w
    self_bottom, self_top = y, y + h
    rect_left, rect_right = xx, xx + ww
    rect_bottom, rect_top = yy, yy + hh

    # Not even touching
    if (self_bottom > rect_top or \
            self_top < rect_bottom or \
            self_left > rect_right or \
            self_right < rect_left):
        return False

    # Discard corner intersects
    if (self_left == rect_right and self_bottom == rect_top or \
            self_left == rect_right and rect_bottom == self_top or \
            rect_left == self_right and self_bottom == rect_top or \
            rect_left == self_right and rect_bottom == self_top):
        return False

    return True


@nb.jit(nopython=True)
def contains(x, y, w, h, xx, yy, ww, hh):
    # does the first rectangle contain the second one?
    return yy >= y and xx >= x and yy + hh <= y + h and xx + ww <= x + w


@nb.jit(nopython=True)
def join(x, y, w, h, xx, yy, ww, hh):

    if contains(x, y, w, h, xx, yy, ww, hh):
        # first rectangle contains the second one, return the first one
        return True, x, y, w, h

    if contains(xx, yy, ww, hh, x, y, w, h):
        # second rectangle contains the first one, return the second one
        return True, xx, yy, ww, hh

    if not intersects(x, y, w, h, xx, yy, ww, hh):
        # cannot join--not intersecting
        return False, x, y, w, h

    if y == yy and h == hh:
        # vertically aligned
        x_min = min(x, xx)
        x_max = max(x + w, xx + ww)
        return True, x_min, y, x_max - x_min, h

    if x == xx and w == ww:
        # horizontally aligned
        y_min = min(y, yy)
        y_max = max(y + h, yy + hh)
        return True, x, y_min, w, y_max - y_min

    return False, x, y, w, h


@jitclass([
    ('sections', nb.int32[:, :]),
    ('next_section', nb.int32),
    ('n_sections', nb.int32),
    ('w', nb.int32),
    ('h', nb.int32),
])
class Packer(object):
    def __init__(self, w, h, n):
        # n = maximum number of sections
        self.sections = np.empty((n, 5), dtype=np.int32)
        self.w = w
        self.h = h
        self.next_section = 0
        self.n_sections = 0
        self.reset()

    def reset(self):
        self.sections.fill(0)
        self.next_section = 0
        self.n_sections = 0
        self.append_section(0, 0, self.w, self.h)

    def append_section(self, x, y, w, h):
        for i in range(self.sections.shape[0]):
            if self.sections[i, DELETION_FLAG] == DELETED:
                self.sections[i, X] = x
                self.sections[i, Y] = y
                self.sections[i, W] = w
                self.sections[i, H] = h
                self.sections[i, DELETION_FLAG] = NOT_DELETED
                self.n_sections += 1
                if i == self.next_section:
                    self.next_section += 1
                return
        # fatal condition: out of space

    def delete_section(self, i):
        self.sections[i, DELETION_FLAG] = DELETED
        self.n_sections -= 1

    def is_deleted(self, i):
        return self.sections[i, DELETION_FLAG] == DELETED

    def add_section(self, x, y, w, h):
        deleting = True
        while self.n_sections > 0 and deleting:
            deleting = False
            for i in range(self.next_section + 1):
                if self.is_deleted(i):
                    continue
                xx = self.sections[i, X]
                yy = self.sections[i, Y]
                ww = self.sections[i, W]
                hh = self.sections[i, H]
                joinp, x, y, w, h = join(x, y, w, h, xx, yy, ww, hh)
                if joinp:
                    self.delete_section(i)
                    deleting = True
        self.append_section(x, y, w, h)

    def split(self, xx, yy, ww, hh, w, h):
        # xx/yy/ww/hh = location and size of section to split
        # w/h = width/height of rect being added
        # short axis split
        # if ww < hh:
        # short leftover axis split
        assert h <= hh
        assert w <= ww
        assert h <= self.h
        assert w <= self.w
        if ww - w < hh - h:
            # split horizontal
            if h < hh:
                self.add_section(xx, yy + h, ww, hh - h)
            if w < ww:
                self.add_section(xx + w, yy, ww - w, h)
        else:
            # split vertical
            if h < hh:
                self.add_section(xx, yy + h, w, hh - h)
            if w < ww:
                self.add_section(xx + w, yy, ww - w, hh)

    def section_fitness(self, i, w, h):
        ww = self.sections[i, W]
        hh = self.sections[i, H]

        # best area fit
        if w > ww or h > hh:
            return DOESNT_FIT

        return (ww * hh) - (w * h)

    def select_fittest_section(self, w, h):
        min_fitness = DOESNT_FIT
        fittest_section = NO_SECTION

        for i in range(self.next_section + 1):
            if self.is_deleted(i):
                continue
            fitness = self.section_fitness(i, w, h)
            if fitness == DOESNT_FIT:
                continue
            if min_fitness == DOESNT_FIT or fitness < min_fitness:
                min_fitness = fitness
                fittest_section = i

        return fittest_section

    def add_rect(self, w, h):
        section = self.select_fittest_section(w, h)
        if section == NO_SECTION:
            return -1, -1
        x = self.sections[section, X]
        y = self.sections[section, Y]
        ww = self.sections[section, W]
        hh = self.sections[section, H]
        self.delete_section(section)
        self.split(x, y, ww, hh, w, h)
        return x, y


@nb.jit(nopython=True)
def pack(w, h, ws, hs, xs, ys, pages):
    n = len(ws)
    p = Packer(w, h, max(n, 128))  # should be enough overhead
    need_more_pages = True
    page = 1
    while need_more_pages:
        p.reset()
        need_more_pages = False
        for i in range(n):
            if pages[i] > 0:  # already placed
                continue
            x, y = p.add_rect(ws[i], hs[i])
            if x == -1 or y == -1:
                need_more_pages = True
                continue
            xs[i], ys[i] = x, y
            pages[i] = page
        page += 1

class Mosaic(object):
    def __init__(self, the_bin, shape=(600, 800), scale=0.33, bg_color=200, coordinates=None):
        self.bin = the_bin
        self.shape = shape
        self.bg_color = bg_color
        self.scale = scale
        self.coordinates = coordinates
        self._shapes = None
    def shapes(self):
        if self._shapes is not None:
            return self._shapes
        hs, ws, ix = [], [], []
        with self.bin:
            if self.bin.schema == SCHEMA_VERSION_1:
                ii = InfilledImages(self.bin)
            else:
                ii = self.bin.images
            for target_number in ii:
                h, w = ii.shape(target_number)
                hs.append(math.floor(h * self.scale))
                ws.append(math.floor(w * self.scale))
                ix.append(target_number)
        self._shapes = (np.array(hs, dtype=np.int32),
                        np.array(ws, dtype=np.int32),
                        np.array(ix, dtype=np.int32))
        return self._shapes
    def pack(self, max_pages=None):
        if self.coordinates is not None:
            return self.coordinates
        hs, ws, ids = self.shapes()
        area = hs * ws
        sort_order = np.flip(np.argsort(area))
        hs = hs[sort_order]
        ws = ws[sort_order]
        ids = ids[sort_order]
        xs = np.zeros(len(ids), dtype=np.int32)
        ys = np.zeros(len(ids), dtype=np.int32)
        pages = np.zeros(len(ids), dtype=np.int32)
        H, W = self.shape

        pack(H, W, hs, ws, ys, xs, pages)

        pages -= 1
        self.coordinates = pd.DataFrame({
            'page': pages,
            'y': ys,
            'x': xs,
            'h': hs,
            'w': ws,
            'roi_number': ids
            })
        return self.coordinates
    def page(self, page=0):
        df = self.pack()
        page_h, page_w = self.shape
        page_image = np.zeros((page_h, page_w), dtype=np.uint8) + self.bg_color
        sdf = df[df.page == page]
        with self.bin:
            if self.bin.schema == SCHEMA_VERSION_1:
                ii = InfilledImages(self.bin)
            else:
                ii = self.bin.images
            for index, row in sdf.iterrows():
                y, x = row.y, row.x
                h, w = row.h, row.w
                unscaled_image = ii[row.roi_number]
                scaled_image = resize(unscaled_image, (h, w), mode='reflect', preserve_range=True)
                page_image[y:y+h, x:x+w] = scaled_image
        return page_image
