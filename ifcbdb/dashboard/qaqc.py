MIN_SIZE = 32

def check_bad(bin):
    """returns True if bin is malformed and impossible to use"""
    if bin.fileset.getsize() < MIN_SIZE:
        return True
    # FIXME add more checks
    return False

def check_no_rois(bin):
    """returns True is there are no rois"""
    roi_size = bin.fileset.getsizes()['roi']
    if roi_size <= 1: # old style empty ROI files are 1 byte long
        return True
    return False
