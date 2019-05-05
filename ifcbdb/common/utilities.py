import base64

from ifcb.data.imageio import format_image


def embed_image(image):
    """
    Converts an IFCB formatted image array into a base64 encoded string that can be shown as an embedded
    image in HTML
    """
    image_data = format_image(image).getvalue()

    return base64.b64encode(image_data).decode('ascii')


# TODO: Default values should come from common settings
def parse_scale_factor(value):
    """
    Attempts to parse a scale factor from the UI (int) into the decimal required by the mosaic classes
    """
    try:
        return float(value) / 100.0
    except:
        return 0.33


# TODO: Default values should come from common settings
def parse_view_size(value):
    """
    Attempts to parse a view size from 000x111 format to the tuple required by the mosaic classes. Note that the input
      string will have width first, whereas the format required by the mosaics has height first
    """
    try:
        dimensions = value.split("x")
        return (int(dimensions[1]), int(dimensions[0]))
    except:
        return (600, 800)
