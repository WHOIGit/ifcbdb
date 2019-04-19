import base64

from ifcb.data.imageio import format_image


def embed_image(image):
    """
    Converts an IFCB formatted image array into a base64 encoded string that can be shown as an embedded
    image in HTML
    """
    image_data = format_image(image).getvalue()

    return base64.b64encode(image_data).decode('ascii')
