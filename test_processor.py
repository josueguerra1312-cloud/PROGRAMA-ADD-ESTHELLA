from processor import filename_folio, make_filename, normalize_folio

def test_source_variants():
    assert normalize_folio('2457-001') == '2457001'
    assert normalize_folio('2457 015') == '2457015'
    assert normalize_folio('2457/036') == '2457036'

def test_final_filename_never_has_folio_hyphen():
    assert filename_folio('2457-001') == '2457001'
    assert make_filename('JAN-07-26', '2457-001') == 'JAN-07-26_2457001.pdf'
    assert make_filename('REVIEW', '2457-018') == 'REVIEW_2457018.pdf'
