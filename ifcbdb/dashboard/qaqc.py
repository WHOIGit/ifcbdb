MIN_SIZE = 32

def check_bad(bin):
    """returns True if bin is malformed and impossible to use"""
    if bin.fileset.getsize() < MIN_SIZE:
        return True
    try:
        len(bin)
    except: # bad ADC data
        return True
    try:
        len(bin.images)
    except:
        return True
    return False

def check_no_rois(bin):
    """returns True if any file is zero length, etc"""
    sizes = bin.fileset.getsizes()
    roi_size = sizes['roi']
    if roi_size <= 1: # old style empty ROI files are 1 byte long
        return True
    hdr_size = sizes['hdr']
    if hdr_size == 0:
        return True
    adc_size = sizes['adc']
    if adc_size == 0:
        return True
    return False
