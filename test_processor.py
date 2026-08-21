from processor import normalize_folio,valid_date_name,make_filename
def test_folio(): assert normalize_folio('2457 015')=='2457-015'
def test_date(): assert valid_date_name(7,1,26)=='JAN-07-26'
def test_bad_date(): assert valid_date_name(31,2,26)=='REVIEW'
def test_name(): assert make_filename('JAN-07-26','2457 015')=='JAN-07-26_2457-015.pdf'
