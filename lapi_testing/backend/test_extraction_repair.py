"""Extraction second chances: invalid output, empty fields and left-out sources."""
import pytest
from jsonschema import ValidationError
from lapi_app.lapi_agent import answer_check, extraction_repair as repair

SCHEMA = {'type': 'object', 'properties': {'total': {'type': ['number', 'null']}, 'vendor': {'type': ['string', 'null']}},
          'required': ['total', 'vendor'], 'additionalProperties': False}


def chunk(id, key):
    return {'id': id, 'document_id': 'merged', 'source_key': key, 'text': id}


def test_a_source_left_out_by_ranking_is_added():
    first, second, third = chunk('a', '1'), chunk('b', '2'), chunk('c', '2')
    chunks, added = repair.cover_sources([first], [first, second, third], 1)
    assert added == ['2'] and [c['id'] for c in chunks] == ['a', 'b']


def test_nothing_changes_when_every_source_is_present():
    first, second = chunk('a', '1'), chunk('b', '2')
    assert repair.cover_sources([first, second], [first, second], 5) == ([first, second], [])


def test_merged_source_without_text_is_reported():
    merge = {'document_id': 'merged', 'sources': [{'key': '1', 'name': 'invoice.pdf'}, {'key': '2', 'name': 'receipt.jpg'}]}
    assert repair.unread_sources([], [chunk('a', '1')], merge) == ['receipt.jpg']


def test_invalid_output_is_retried_with_the_schema_error():
    seen = []
    def call(text, schema, sources):
        seen.append(text)
        return ({'total': 'many', 'vendor': 'A'} if len(seen) == 1 else {'total': 5, 'vendor': 'A'}), []
    assert repair.generate_valid(call, 'doc', SCHEMA, [])[0]['total'] == 5
    assert 'total' in seen[1] and seen[1].endswith('doc')


def test_output_invalid_twice_still_fails():
    with pytest.raises(ValidationError):
        repair.generate_valid(lambda *a: ({'total': 'many', 'vendor': 'A'}, []), 'doc', SCHEMA, [])


def test_empty_field_is_filled_only_with_a_quote():
    first = {'total': None, 'vendor': None}
    keys = repair.missing_fields(first, SCHEMA)
    assert keys == ['total', 'vendor']
    answer = {'total': 5, 'vendor': 'Invented'}
    quote = {'field': '/total', 'chunk_id': 'a', 'quote': '5'}
    result, evidence, filled = repair.fill_missing(lambda *a: (answer, [quote]), first, [], SCHEMA, keys, 'doc', [])
    assert result == {'total': 5, 'vendor': None} and evidence == [quote] and filled == ['total']


def test_second_pass_only_sees_the_empty_fields():
    subset = repair.subset_schema(SCHEMA, ['vendor'])
    assert list(subset['properties']) == ['vendor'] and subset['required'] == ['vendor']


def test_a_filled_value_that_breaks_the_schema_is_dropped():
    first = {'total': None, 'vendor': 'A'}
    quote = {'field': '/total', 'chunk_id': 'a', 'quote': 'x'}
    assert repair.fill_missing(lambda *a: ({'total': 'x'}, [quote]), first, [], SCHEMA, ['total'], 'doc', [])[0] == first


def test_month_name_dates_match_across_formats():
    source = [{'index': 1, 'text': 'Deadline: 15 Mar 2026'}]
    assert answer_check.unsupported_values('The deadline is March 15, 2026 [1].', source) == []
