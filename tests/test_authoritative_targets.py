import copy
import json
from pathlib import Path

import pytest
import import_target_universe as importer

ROOT = Path(__file__).resolve().parents[1]


def setup_source(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path('data').mkdir()
    data = json.loads((ROOT / 'data/authoritative_target_companies.json').read_text())
    Path('data/authoritative_target_companies.json').write_text(json.dumps(data))
    return data


def test_authoritative_162_before_exclusions(tmp_path, monkeypatch):
    setup_source(tmp_path, monkeypatch)
    # Poison the old fallback: it must not change the source universe.
    Path('data/target_programs.json').write_text(json.dumps([{'company': 'Corrupted'}] * 204))
    rows, source, sheet = importer.load_rows()
    assert len(rows) == 162
    assert source == importer.SOURCE_WORKBOOK
    assert sheet == 'Target Companies'
    importer.main()
    active = json.loads(Path('data/target_programs.json').read_text())
    archived = json.loads(Path('data/excluded_target_programs.json').read_text())
    report = json.loads(Path('data/company_reconciliation_report.json').read_text())
    assert report['authoritative_source_records_before_exclusions'] == 162
    assert len(active) + len(archived) == 162
    assert {r['original_spreadsheet_row_number'] for r in active + archived} == {r['_row'] for r in rows}
    assert all(r['archive_reason'] for r in archived)
    assert all(r['company'] != 'Corrupted' for r in active)


def test_legacy_probability_cannot_change_campaign(tmp_path, monkeypatch):
    data = setup_source(tmp_path, monkeypatch)
    importer.main()
    outputs = ['target_programs', 'company_watchlist', 'excluded_target_programs', 'company_reconciliation_report']
    before = {name: Path(f'data/{name}.json').read_text() for name in outputs}
    for r in data['records']:
        r['legacy_unvalidated_probability_text'] = 'quant insurance defense P(offer): 100% PRIORITY #1'
    Path('data/authoritative_target_companies.json').write_text(json.dumps(data))
    importer.main()
    assert before == {name: Path(f'data/{name}.json').read_text() for name in outputs}
    assert all('legacy_unvalidated_probability_text' not in text for text in before.values())


def test_missing_authority_never_falls_back(tmp_path, monkeypatch):
    setup_source(tmp_path, monkeypatch)
    Path('data/authoritative_target_companies.json').unlink()
    Path('data/target_programs.json').write_text(json.dumps([{'company': 'Corrupted'}] * 204))
    with pytest.raises(FileNotFoundError, match='Missing authoritative input'):
        importer.load_rows()


def test_corrupted_authoritative_count_rejected(tmp_path, monkeypatch):
    data = setup_source(tmp_path, monkeypatch)
    data['records'] += copy.deepcopy(data['records'][:42])
    Path('data/authoritative_target_companies.json').write_text(json.dumps(data))
    with pytest.raises(ValueError, match='exactly 162'):
        importer.load_rows()


def test_current_exclusions_remain_auditable(tmp_path, monkeypatch):
    data = setup_source(tmp_path, monkeypatch)
    data['records'][0]['category'] = 'Insurance'
    data['records'][1]['internship_program'] = 'Quant Trading Intern'
    Path('data/authoritative_target_companies.json').write_text(json.dumps(data))
    importer.main()
    archived = {r['company']: r for r in json.loads(Path('data/excluded_target_programs.json').read_text())}
    assert archived[data['records'][0]['company']]['archive_reason'] == 'insurance'
    assert archived[data['records'][1]['company']]['archive_reason'] == 'quant'


def test_exact_workbook_and_url_only_rows(tmp_path, monkeypatch):
    from openpyxl import Workbook
    data = setup_source(tmp_path, monkeypatch)
    book = Workbook()
    sheet = book.active
    sheet.title = 'Target Companies'
    headers = list(importer.FIELD_MAP) + ['Legacy probability']
    sheet.append(headers)
    for r in data['records']:
        sheet.append([r[v] for v in importer.FIELD_MAP.values()] + ['quant insurance 100% offer'])
    sheet.append(['https://unrelated.example'])
    sheet.append(['', '', '', '', '', '', 'https://another.example'])
    other = book.create_sheet('Unrelated')
    other.append(['Company'])
    other.append(['Not a target'])
    book.save(importer.SOURCE_WORKBOOK)
    rows, _, _ = importer.load_rows()
    assert len(rows) == 162
    assert all('Legacy probability' not in r for r in rows)
    assert [r['Company'] for r in rows] == [r['company'] for r in data['records']]
