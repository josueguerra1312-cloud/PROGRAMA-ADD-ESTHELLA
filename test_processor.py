from processor import make_filename, normalize_date, normalize_folio

def test_valid_date(): assert normalize_date("jan-07-26") == "JAN-07-26"
def test_invalid_date(): assert normalize_date("FEB-31-26") == "REVIEW"
def test_folio(): assert normalize_folio("2457 015") == "2457-015"
def test_filename(): assert make_filename("JAN-07-26", "2457 015") == "JAN-07-26_2457-015.pdf"
