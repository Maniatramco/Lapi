"""Admin token usage report and versioned model prices.

Every figure comes from lapi_token_usage rows (one per provider call). Costs are
approximate: tokens x the price version that was in force when the call was
made, in Decimal, per currency (currencies are never added together). Calls
without a provider report and calls without a price are counted, not priced.
"""
import csv
import io
import time
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select

from . import core
from .lapi_agent import token_usage
from .usage_tables import TokenUsage, ModelPrice

ROW_LIMIT = 200000
GROUPS = ('dataset', 'model', 'day', 'user')
MAX_PRICE = Decimal(1000000)


def administrator(actor):
    if not core.is_administrator(actor):
        raise HTTPException(403, 'Only an administrator can view token usage and model prices.')


def price_value(value, required):
    if value is None or value == '':
        if required:
            raise ValueError('Enter a price per 1M tokens.')
        return None
    if isinstance(value, bool):
        raise ValueError('Enter a number.')
    amount = token_usage.decimal(value)
    if amount is None:
        raise ValueError('Enter a non-negative number.')
    if amount > MAX_PRICE or amount.as_tuple().exponent < -12:
        raise ValueError('Enter at most 1,000,000 with up to 12 decimal places.')
    return token_usage.amount_text(amount)


class PriceInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    currency: str = Field(pattern=r'^[A-Za-z]{3}$')
    input_price: str | int | float
    cached_input_price: str | int | float | None = None
    cache_write_price: str | int | float | None = None
    output_price: str | int | float
    reasoning_price: str | int | float | None = None
    effective_at: float | str | None = None

    @field_validator('input_price', 'output_price', mode='before')
    @classmethod
    def required_price(cls, value):
        return price_value(value, True)

    @field_validator('cached_input_price', 'cache_write_price', 'reasoning_price', mode='before')
    @classmethod
    def optional_price(cls, value):
        return price_value(value, False)


def epoch(value, default=None, end_of_day=False):
    """Seconds since the epoch from a number, an ISO date (UTC) or an ISO datetime."""
    if value in (None, ''):
        return default
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    try:
        text = str(value).strip()
        if len(text) == 10:
            day = datetime.strptime(text, '%Y-%m-%d').replace(tzinfo=timezone.utc)
            return (day + timedelta(days=1)).timestamp() if end_of_day else day.timestamp()
        moment = datetime.fromisoformat(text.replace('Z', '+00:00'))
        return (moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)).timestamp()
    except ValueError:
        raise HTTPException(400, 'Use dates as YYYY-MM-DD.') from None


def day_of(stamp):
    return datetime.fromtimestamp(stamp, timezone.utc).strftime('%Y-%m-%d')


def model_record(session, model_id):
    record = session.get(core.Record, model_id)
    if not record or record.kind != 'model':
        raise HTTPException(404, 'Model registration not found.')
    return record


def call_of(row):
    return {key: getattr(row, key) for key in token_usage.COUNT_KEYS}


def aggregate(rows, prices, model_names=None):
    totals = {key: 0 for key in token_usage.COUNT_KEYS}
    reported = 0
    costs = []
    latency = []
    per_model = {}
    for row in rows:
        if row.reported:
            reported += 1
        for key in token_usage.COUNT_KEYS:
            value = getattr(row, key)
            if value is not None:
                totals[key] += value
        if row.latency_ms is not None:
            latency.append(row.latency_ms)
        costs.append(token_usage.call_cost(call_of(row), prices.get(row.price_version_id)))
        key = model_key(row)
        per_model[key] = per_model.get(key, 0) + (row.input_tokens or 0) + (row.output_tokens or 0)
    top = max(per_model.items(), key=lambda item: item[1])[0] if per_model else None
    return {**totals, 'total_tokens': totals['input_tokens'] + totals['output_tokens'],
            'model_calls': len(rows), 'reported_calls': reported, 'not_reported_calls': len(rows) - reported,
            'cache_hit_rate': round(totals['cached_input_tokens'] / totals['input_tokens'], 4) if totals['input_tokens'] else None,
            'avg_latency_ms': round(sum(latency) / len(latency)) if latency else None,
            'top_model': top, 'top_model_label': (model_names or {}).get(top, top) if top else None,
            'cost': token_usage.cost_summary(costs)}


def model_key(row):
    return row.model_id or ('provider:' + row.provider_model if row.provider_model else 'unknown')


def group_key(row, group_by):
    if group_by == 'dataset':
        return row.dataset_id or 'none'
    if group_by == 'model':
        return model_key(row)
    if group_by == 'user':
        return row.owner_id or 'none'
    return day_of(row.created_at)


def query_rows(session, start, end, dataset_id, model_id, owner_id, stage):
    statement = select(TokenUsage)
    if start is not None:
        statement = statement.where(TokenUsage.created_at >= start)
    if end is not None:
        statement = statement.where(TokenUsage.created_at < end)
    if dataset_id == 'none':
        statement = statement.where(TokenUsage.dataset_id.is_(None))
    elif dataset_id:
        statement = statement.where(TokenUsage.dataset_id == dataset_id)
    if model_id:
        if model_id.startswith('provider:'):
            statement = statement.where(TokenUsage.model_id.is_(None), TokenUsage.provider_model == model_id[9:])
        else:
            statement = statement.where(TokenUsage.model_id == model_id)
    if owner_id:
        statement = statement.where(TokenUsage.owner_id == owner_id)
    if stage:
        statement = statement.where(TokenUsage.stage == stage)
    rows = list(session.scalars(statement.order_by(TokenUsage.created_at, TokenUsage.id).limit(ROW_LIMIT + 1)))
    return rows[:ROW_LIMIT], len(rows) > ROW_LIMIT


def load_prices(session, rows):
    ids = sorted({row.price_version_id for row in rows if row.price_version_id})
    prices = {}
    for start in range(0, len(ids), 500):
        for version in session.scalars(select(ModelPrice).where(ModelPrice.id.in_(ids[start:start + 500]))):
            prices[version.id] = token_usage.price_public(version)
    return prices


def labels(session):
    records = list(session.scalars(select(core.Record).where(core.Record.kind.in_(('knowledge_base', 'model')))))
    datasets = {r.id: r.name for r in records if r.kind == 'knowledge_base'}
    models = {r.id: r.name for r in records if r.kind == 'model'}
    users = {u.id: u.username for u in session.scalars(select(core.User))}
    return datasets, models, users


def report(session, start, end, dataset_id='', model_id='', owner_id='', stage='', group_by='dataset'):
    rows, truncated = query_rows(session, start, end, dataset_id, model_id, owner_id, stage)
    prices = load_prices(session, rows)
    datasets, models, users = labels(session)
    model_names = {key: models.get(key) or (key[9:] if key.startswith('provider:') else key) for key in {model_key(r) for r in rows}}
    for row in rows:
        if row.model_id and row.model_id not in models and row.provider_model:
            model_names[row.model_id] = row.provider_model

    def label(kind, key):
        if kind == 'dataset':
            return 'No dataset' if key == 'none' else datasets.get(key, key)
        if kind == 'model':
            return model_names.get(key, key)
        if kind == 'user':
            return 'Unknown' if key == 'none' else users.get(key, key)
        return key

    def grouped(kind):
        buckets = {}
        for row in rows:
            buckets.setdefault(group_key(row, kind), []).append(row)
        result = [{'key': key, 'label': label(kind, key), **aggregate(items, prices, model_names)} for key, items in buckets.items()]
        if kind == 'day':
            return sorted(result, key=lambda item: item['key'])
        return sorted(result, key=lambda item: (-item['total_tokens'], -item['model_calls'], str(item['label'])))

    by_dataset = grouped('dataset')
    for item in by_dataset:
        members = [row for row in rows if group_key(row, 'dataset') == item['key']]
        for field, name in (('conversation_id', 'conversations'), ('job_id', 'jobs')):
            buckets = {}
            for row in members:
                if getattr(row, field):
                    buckets.setdefault(getattr(row, field), []).append(row)
            item[name] = sorted(({'id': key, 'total_tokens': sum((r.input_tokens or 0) + (r.output_tokens or 0) for r in values),
                                  'model_calls': len(values), 'last_at': max(r.created_at for r in values)}
                                 for key, values in buckets.items()), key=lambda entry: -entry['last_at'])[:20]
    days = {}
    for row in rows:
        day = days.setdefault(day_of(row.created_at), {})
        key = model_key(row)
        day[key] = day.get(key, 0) + (row.input_tokens or 0) + (row.output_tokens or 0)
    return {'filters': {'start': start, 'end': end, 'dataset_id': dataset_id or None, 'model_id': model_id or None,
                        'owner_id': owner_id or None, 'stage': stage or None},
            'group_by': group_by, 'approximate_cost': True, 'truncated': truncated,
            'totals': aggregate(rows, prices, model_names),
            'groups': grouped(group_by), 'by_dataset': by_dataset, 'by_model': grouped('model'),
            'by_day': [{'day': key, 'models': value, 'total_tokens': sum(value.values())} for key, value in sorted(days.items())],
            'options': {'datasets': sorted(({'id': k, 'name': v} for k, v in datasets.items()), key=lambda x: x['name'].casefold()),
                        'models': sorted(({'id': k, 'name': v} for k, v in model_names.items()), key=lambda x: str(x['name']).casefold()),
                        'users': sorted(({'id': k, 'name': v} for k, v in users.items()), key=lambda x: x['name'].casefold()),
                        'stages': list(token_usage.STAGES)}}


def safe_cell(value):
    """Spreadsheet-safe CSV cell: user-controlled names never become formulas."""
    if value is None:
        return ''
    text = str(value)
    return "'" + text if text[:1] in ('=', '+', '-', '@', '\t', '\r') else text


def export_csv(session, rows):
    prices = load_prices(session, rows)
    datasets, models, users = labels(session)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(['time_utc', 'user', 'dataset_id', 'dataset', 'conversation_id', 'message_id', 'job_id',
                     'model_id', 'model', 'provider_model', 'stage', 'input_tokens', 'cached_input_tokens',
                     'cache_write_tokens', 'output_tokens', 'reasoning_tokens', 'latency_ms', 'reported',
                     'price_version_id', 'currency', 'approximate_cost'])
    for row in rows:
        status, amount, currency = token_usage.call_cost(call_of(row), prices.get(row.price_version_id))
        cost = token_usage.amount_text(amount) if status == 'priced' else 'Not reported' if status == 'not_reported' else 'Price not set'
        writer.writerow([safe_cell(v) for v in (
            datetime.fromtimestamp(row.created_at, timezone.utc).isoformat(timespec='seconds'),
            users.get(row.owner_id, row.owner_id), row.dataset_id, datasets.get(row.dataset_id, ''),
            row.conversation_id, row.message_id, row.job_id, row.model_id, models.get(row.model_id, ''),
            row.provider_model, row.stage, row.input_tokens, row.cached_input_tokens, row.cache_write_tokens,
            row.output_tokens, row.reasoning_tokens, row.latency_ms, 'yes' if row.reported else 'no',
            row.price_version_id, currency or '', cost)])
    return out.getvalue()


def install(app, auth):
    def filters(start: str = '', end: str = '', dataset_id: str = Query('', max_length=80),
                model_id: str = Query('', max_length=340), owner_id: str = Query('', max_length=80),
                stage: str = Query('', max_length=32)):
        if stage and stage not in token_usage.STAGES:
            raise HTTPException(400, 'Choose a known stage.')
        return {'start': epoch(start), 'end': epoch(end, end_of_day=True), 'dataset_id': dataset_id,
                'model_id': model_id, 'owner_id': owner_id, 'stage': stage}

    @app.get('/api/admin/token-usage')
    def usage(owner=Depends(auth), selected=Depends(filters),
              group_by: Literal['dataset', 'model', 'day', 'user'] = 'dataset'):
        administrator(owner)
        with core.Session() as session:
            return report(session, selected['start'], selected['end'], selected['dataset_id'], selected['model_id'],
                          selected['owner_id'], selected['stage'], group_by)

    @app.get('/api/admin/token-usage/export')
    def export(owner=Depends(auth), selected=Depends(filters)):
        administrator(owner)
        with core.Session() as session:
            rows, _ = query_rows(session, selected['start'], selected['end'], selected['dataset_id'],
                                 selected['model_id'], selected['owner_id'], selected['stage'])
            text = export_csv(session, rows)
        return Response(text, media_type='text/csv; charset=utf-8',
                        headers={'Content-Disposition': 'attachment; filename="lapi-token-usage.csv"', 'Cache-Control': 'no-store'})

    @app.get('/api/model-registrations/{id}/prices')
    def prices(id: str, owner=Depends(auth)):
        administrator(owner)
        with core.Session() as session:
            model_record(session, id)
            versions = list(session.scalars(select(ModelPrice).where(ModelPrice.model_id == id)))
        current = token_usage.price_in_force(versions, time.time())
        ordered = sorted(versions, key=lambda v: (v.effective_at, v.created_at or 0), reverse=True)
        return {'model_id': id, 'current': token_usage.price_public(current),
                'versions': [token_usage.price_public(v) for v in ordered]}

    @app.post('/api/model-registrations/{id}/prices')
    def add_price(id: str, body: PriceInput, owner=Depends(auth)):
        administrator(owner)
        now = time.time()
        effective = epoch(body.effective_at, now)
        with core.Session.begin() as session:
            model_record(session, id)
            version = ModelPrice(id=core.uid(), model_id=id, currency=body.currency.upper(),
                                 input_price=body.input_price, cached_input_price=body.cached_input_price,
                                 cache_write_price=body.cache_write_price, output_price=body.output_price,
                                 reasoning_price=body.reasoning_price, effective_at=effective,
                                 created_at=now, created_by=owner)
            session.add(version)
            public = token_usage.price_public(version)
        # Earlier calls keep the version stored on their usage rows.
        return public

    @app.get('/api/token-usage/conversations/{id}')
    def conversation_totals(id: str, owner=Depends(auth)):
        """The signed-in user's own totals for one conversation."""
        with core.Session() as session:
            rows = list(session.scalars(select(TokenUsage).where(TokenUsage.conversation_id == id, TokenUsage.owner_id == owner)))
            prices = load_prices(session, rows)
        return {'conversation_id': id, **aggregate(rows, prices)}
