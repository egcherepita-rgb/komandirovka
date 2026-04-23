from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .models import Slot

BASE_DIR = Path(__file__).resolve().parent

DEFAULT_STATUSES = ['Свободно', 'Предзапрос', 'Забронировано', 'Отменено', 'Отпуск']
DEFAULT_PRIORITIES = ['Высокий', 'Средний', 'Низкий']

app = FastAPI(title='Календарь командировок')
app.mount('/static', StaticFiles(directory=str(BASE_DIR / 'static')), name='static')
templates = Jinja2Templates(directory=str(BASE_DIR / 'templates'))


@app.on_event('startup')
def startup_event() -> None:
    Base.metadata.create_all(bind=engine)


def status_class(status: str) -> str:
    mapping = {
        'Свободно': 'free',
        'Предзапрос': 'pre',
        'Забронировано': 'booked',
        'Отменено': 'cancelled',
        'Отпуск': 'vacation',
    }
    return mapping.get(status, 'free')


def distinct_values(db: Session, column) -> list[str]:
    return [row[0] for row in db.execute(select(column).distinct().where(column.is_not(None)).order_by(column)).all() if row[0]]


def load_meta(db: Session) -> dict:
    db_statuses = distinct_values(db, Slot.status)
    db_priorities = distinct_values(db, Slot.priority)
    return {
        'statuses': list(dict.fromkeys(DEFAULT_STATUSES + db_statuses)),
        'priorities': list(dict.fromkeys(DEFAULT_PRIORITIES + db_priorities)),
        'branches': distinct_values(db, Slot.branch),
        'directions': distinct_values(db, Slot.product_direction),
    }


def normalize_code_part(value: str) -> str:
    cleaned = re.sub(r'[^A-Za-zА-Яа-я0-9]+', '-', value.strip())
    return cleaned.strip('-').lower() or 'slot'


def make_slot_code(week: int, product_direction: str) -> str:
    return f'w{week}-{normalize_code_part(product_direction)}'


templates.env.filters['status_class'] = status_class


@app.get('/', response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    slots = db.execute(select(Slot).order_by(Slot.product_direction, Slot.week)).scalars().all()
    if not slots:
        return templates.TemplateResponse('empty.html', {'request': request})

    directions = sorted({s.product_direction for s in slots})
    weeks = sorted({s.week for s in slots})
    periods = {s.week: s.period for s in slots}

    matrix: dict[str, dict[int, Slot | None]] = defaultdict(dict)
    for slot in slots:
        matrix[slot.product_direction][slot.week] = slot

    total = len(slots)
    stats = {
        'total': total,
        'free': sum(1 for s in slots if s.status == 'Свободно'),
        'pre': sum(1 for s in slots if s.status == 'Предзапрос'),
        'booked': sum(1 for s in slots if s.status == 'Забронировано'),
        'cancelled': sum(1 for s in slots if s.status == 'Отменено'),
        'vacation': sum(1 for s in slots if s.status == 'Отпуск'),
    }

    return templates.TemplateResponse(
        'dashboard.html',
        {
            'request': request,
            'directions': directions,
            'weeks': weeks,
            'periods': periods,
            'matrix': matrix,
            'stats': stats,
        },
    )


@app.get('/slots', response_class=HTMLResponse)
def slots_page(
    request: Request,
    week: int | None = None,
    product_direction: str | None = None,
    status: str | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
):
    query = select(Slot)
    if week:
        query = query.where(Slot.week == week)
    if product_direction:
        query = query.where(Slot.product_direction == product_direction)
    if status:
        query = query.where(Slot.status == status)
    if q:
        like = f'%{q.strip()}%'
        query = query.where(
            or_(
                Slot.branch.ilike(like),
                Slot.contact.ilike(like),
                Slot.visit_goal.ilike(like),
                Slot.comment.ilike(like),
            )
        )

    slots = db.execute(query.order_by(Slot.week, Slot.product_direction)).scalars().all()
    meta = load_meta(db)
    weeks = [r[0] for r in db.execute(select(Slot.week).distinct().order_by(Slot.week)).all()]

    return templates.TemplateResponse(
        'slots.html',
        {
            'request': request,
            'slots': slots,
            'meta': meta,
            'weeks': weeks,
            'filters': {
                'week': week,
                'product_direction': product_direction,
                'status': status,
                'q': q or '',
            },
        },
    )


@app.get('/slots/new', response_class=HTMLResponse)
def new_slot_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse('slot_new.html', {'request': request, 'meta': load_meta(db)})


@app.post('/slots/new')
def create_slot(
    week: int = Form(...),
    period: str = Form(...),
    product_direction: str = Form(...),
    status: str = Form('Свободно'),
    branch: str | None = Form(None),
    contact: str | None = Form(None),
    visit_goal: str | None = Form(None),
    priority: str | None = Form(None),
    comment: str | None = Form(None),
    db: Session = Depends(get_db),
):
    week = int(week)
    period = period.strip()
    product_direction = product_direction.strip()
    if not period or not product_direction:
        raise HTTPException(status_code=400, detail='Заполните период и товарное направление')

    existing = db.execute(
        select(Slot).where(Slot.week == week, Slot.product_direction == product_direction)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail='Такой слот уже существует для этой недели и направления')

    slot = Slot(
        week=week,
        period=period,
        product_direction=product_direction,
        status=status.strip() or 'Свободно',
        branch=(branch or '').strip() or None,
        contact=(contact or '').strip() or None,
        visit_goal=(visit_goal or '').strip() or None,
        priority=(priority or '').strip() or None,
        comment=(comment or '').strip() or None,
        slot_code=make_slot_code(week, product_direction),
    )
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return RedirectResponse(url=f'/slot/{slot.id}', status_code=303)


@app.get('/slot/{slot_id}', response_class=HTMLResponse)
def slot_detail(request: Request, slot_id: int, db: Session = Depends(get_db)):
    slot = db.get(Slot, slot_id)
    if not slot:
        raise HTTPException(status_code=404, detail='Слот не найден')
    return templates.TemplateResponse(
        'slot_detail.html',
        {'request': request, 'slot': slot, 'meta': load_meta(db)},
    )


@app.post('/slot/{slot_id}')
def update_slot(
    slot_id: int,
    status: str = Form(...),
    branch: str | None = Form(None),
    contact: str | None = Form(None),
    visit_goal: str | None = Form(None),
    priority: str | None = Form(None),
    comment: str | None = Form(None),
    redirect_to: str | None = Form('/slots'),
    db: Session = Depends(get_db),
):
    slot = db.get(Slot, slot_id)
    if not slot:
        raise HTTPException(status_code=404, detail='Слот не найден')

    slot.status = status.strip()
    slot.branch = (branch or '').strip() or None
    slot.contact = (contact or '').strip() or None
    slot.visit_goal = (visit_goal or '').strip() or None
    slot.priority = (priority or '').strip() or None
    slot.comment = (comment or '').strip() or None
    db.add(slot)
    db.commit()

    return RedirectResponse(url=redirect_to or '/slots', status_code=303)


@app.post('/slot/{slot_id}/delete')
def delete_slot(slot_id: int, db: Session = Depends(get_db)):
    slot = db.get(Slot, slot_id)
    if not slot:
        raise HTTPException(status_code=404, detail='Слот не найден')
    db.delete(slot)
    db.commit()
    return RedirectResponse(url='/slots', status_code=303)


@app.get('/api/summary')
def api_summary(db: Session = Depends(get_db)):
    total = db.scalar(select(func.count()).select_from(Slot)) or 0
    by_status = db.execute(select(Slot.status, func.count()).group_by(Slot.status)).all()
    by_direction = db.execute(
        select(Slot.product_direction, func.count()).group_by(Slot.product_direction).order_by(Slot.product_direction)
    ).all()
    return {
        'total': total,
        'by_status': [{'status': status, 'count': count} for status, count in by_status],
        'by_direction': [{'product_direction': direction, 'count': count} for direction, count in by_direction],
    }
