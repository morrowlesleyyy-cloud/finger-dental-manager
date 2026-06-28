"""MEYA Dental Management System - Main Application"""
import os
import sys
import json
import uuid
from datetime import datetime, date, timedelta
from flask import (Flask, render_template, request, jsonify, redirect,
                   url_for, flash, Response, send_from_directory, session as flask_session,
                   make_response)
from sqlalchemy import func, extract, or_
from functools import wraps

# Add parent dir for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'meya-dental-dev-key')

# Database - support DATABASE_PATH env for Docker
_env_db = os.environ.get('DATABASE_PATH')
if _env_db:
    db_path = _env_db
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
else:
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'clinic.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}?timeout=30'
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'connect_args': {'timeout': 30},
}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

from models import db, Patient, Appointment, Transaction, Employee, PatientImage, TreatmentPlan, CostItem, Consultation
db.init_app(app)

# =================== Auth Configuration ===================
# Change these via environment variables
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

# Store current user info in flask_session keys:
# logged_in, username, user_role, user_id
# role: 'admin' or 'staff'

def login_required(f):
    """Require valid session for route."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not flask_session.get('logged_in'):
            # API routes return 401, page routes redirect
            if request.path.startswith('/api/'):
                return jsonify({'error': 'unauthorized'}), 401
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated

def normalize_phone(phone):
    """Ensure phone starts with '60' (Malaysia country code)."""
    if not phone:
        return None
    if not phone.startswith('60'):
        return '60' + phone
    return phone


def no_cache(response):
    """Add headers to prevent caching of protected pages."""
    if isinstance(response, str):
        response = make_response(response)
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


# Global auth check - protect all routes except login and static
PUBLIC_PATHS = ['/login', '/api/login', '/api/logout', '/static/', '/api/auth/check', '/api/health', '/health']

@app.before_request
def check_global_auth():
    if request.method == 'OPTIONS':
        return None
    path = request.path
    # Allow public paths
    for public in PUBLIC_PATHS:
        if path == public or path.startswith(public):
            return None
    # Check session
    if not flask_session.get('logged_in'):
        if path.startswith('/api/'):
            return jsonify({'error': 'unauthorized'}), 401
        return redirect(url_for('login_page'))

# =================== SSE 客户端管理 ===================
sse_clients = []

def sse_broadcast(event, data):
    """推送 SSE 事件给所有连接的客户端"""
    msg = f'event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n'
    dead = []
    for queue in sse_clients:
        try:
            queue.put(msg)
        except Exception:
            dead.append(queue)
    for q in dead:
        sse_clients.remove(q)

# =================== 创建表 (auto-import handles this) ===================

# =================== Auth Routes ===================

@app.route('/login', methods=['GET'])
def login_page():
    if flask_session.get('logged_in'):
        return redirect(url_for('index'))
    return render_template('login.html')


@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    username = data.get('username', '')
    password = data.get('password', '')
    
    # Check admin (super user)
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        flask_session['logged_in'] = True
        flask_session['username'] = username
        flask_session['user_role'] = 'admin'
        flask_session['user_id'] = 0
        flask_session['display_name'] = username
        flask_session['employee_type'] = 'clinic_staff'
        flask_session['permissions'] = {
            'can_view_appointments': True,
            'can_view_transactions': True,
            'can_edit_patients': True,
            'can_view_reports': True,
            'can_view_performance': True,
            'can_view_images': True,
            'can_view_treatment_plans': True,
            'can_view_consultations': True,
            'is_admin': True,
        }
        return jsonify({'success': True, 'role': 'admin'})
    
    # Check employee accounts
    emp = Employee.query.filter_by(username=username, is_active=True).first()
    if emp and emp.password == password:
        flask_session['logged_in'] = True
        flask_session['username'] = emp.username
        flask_session['user_role'] = emp.role
        flask_session['user_id'] = emp.id
        flask_session['display_name'] = emp.display_name or emp.username
        flask_session['employee_type'] = emp.employee_type or 'clinic_staff'
        flask_session['permissions'] = {
            'can_view_appointments': emp.can_view_appointments,
            'can_view_transactions': emp.can_view_transactions,
            'can_edit_patients': emp.can_edit_patients,
            'can_view_reports': emp.can_view_reports,
            'can_view_performance': emp.can_view_performance,
            'can_view_images': emp.can_view_images,
            'can_view_treatment_plans': emp.can_view_treatment_plans,
            'can_view_consultations': emp.can_view_consultations,
            'is_admin': emp.role == 'admin',
        }
        return jsonify({'success': True, 'role': emp.role})
    
    return jsonify({'success': False, 'error': '用户名或密码错误'}), 401


@app.route('/api/logout', methods=['POST'])
def api_logout():
    flask_session.clear()
    return jsonify({'success': True})


@app.route('/api/auth/check')
def api_auth_check():
    return jsonify({
        'logged_in': flask_session.get('logged_in', False),
        'username': flask_session.get('username', ''),
        'display_name': flask_session.get('display_name', ''),
        'role': flask_session.get('user_role', ''),
        'permissions': flask_session.get('permissions', {}),
    })


# =================== Employee Management API ===================

@app.route('/employees')
def employees_page():
    return no_cache(render_template('base.html'))


@app.route('/api/employees')
def api_list_employees():
    # Admin check
    if flask_session.get('user_role') != 'admin':
        return jsonify({'error': 'forbidden', 'message': '仅管理员可执行此操作'}), 403
    employees = Employee.query.order_by(Employee.id).all()
    return jsonify({'data': [e.to_dict() for e in employees]})


@app.route('/api/employees', methods=['POST'])
def api_create_employee():
    if flask_session.get('user_role') != 'admin':
        return jsonify({'error': 'forbidden', 'message': '仅管理员可执行此操作'}), 403
    data = request.get_json()
    username = data.get('username', '').strip()
    if not username:
        return jsonify({'error': '请输入用户名'}), 400
    password = data.get('password', '').strip()
    if not password:
        return jsonify({'error': '请输入密码'}), 400
    
    if Employee.query.filter_by(username=username).first():
        return jsonify({'error': '用户名已存在'}), 400
    
    emp = Employee(
        username=username,
        password=password,
        display_name=data.get('display_name', ''),
        role='staff',
        employee_type=data.get('employee_type', 'clinic_staff'),
        can_view_appointments=data.get('can_view_appointments', True),
        can_view_transactions=data.get('can_view_transactions', True),
        can_edit_patients=data.get('can_edit_patients', True),
        can_view_reports=data.get('can_view_reports', True),
        can_view_performance=data.get('can_view_performance', True),
        can_view_images=data.get('can_view_images', True),
        can_view_treatment_plans=data.get('can_view_treatment_plans', True),
        can_view_consultations=data.get('can_view_consultations', True),
    )
    db.session.add(emp)
    db.session.commit()
    return jsonify({'success': True, 'data': emp.to_dict()})


@app.route('/api/employees/<int:eid>', methods=['PUT'])
def api_update_employee(eid):
    if flask_session.get('user_role') != 'admin':
        return jsonify({'error': 'forbidden', 'message': '仅管理员可执行此操作'}), 403
    emp = Employee.query.get_or_404(eid)
    data = request.get_json()
    
    if 'username' in data:
        u = data['username'].strip()
        if u and u != emp.username:
            if Employee.query.filter_by(username=u).first():
                return jsonify({'error': '用户名已存在'}), 400
            emp.username = u
    if 'password' in data and data['password'].strip():
        emp.password = data['password'].strip()
    if 'display_name' in data:
        emp.display_name = data['display_name']
    if 'employee_type' in data:
        emp.employee_type = data['employee_type']
    for field in ['can_view_appointments', 'can_view_transactions', 'can_edit_patients',
                  'can_view_reports', 'can_view_performance', 'can_view_images',
                  'can_view_treatment_plans', 'can_view_consultations', 'is_active']:
        if field in data:
            setattr(emp, field, bool(data[field]))
    
    db.session.commit()
    return jsonify({'success': True, 'data': emp.to_dict()})


@app.route('/api/employees/<int:eid>', methods=['DELETE'])
def api_delete_employee(eid):
    if flask_session.get('user_role') != 'admin':
        return jsonify({'error': 'forbidden', 'message': '仅管理员可执行此操作'}), 403
    emp = Employee.query.get_or_404(eid)
    db.session.delete(emp)
    db.session.commit()
    return jsonify({'success': True})


# =================== 主页 / Dashboard ===================

@app.route('/')
def index():
    return no_cache(render_template('base.html'))


@app.route('/api/dashboard')
def api_dashboard():
    # Auto-detect latest month with transaction data, fallback to current month
    latest_txn = Transaction.query.filter(
        Transaction.payment_date.isnot(None)
    ).order_by(Transaction.payment_date.desc()).first()
    if latest_txn and latest_txn.payment_date:
        ref_date = latest_txn.payment_date
    else:
        ref_date = date.today()
    today = date.today()
    month_start = date(ref_date.year, ref_date.month, 1)

    # Staff data isolation helpers
    staff = _staff_name()
    def _appt_q(base=None):
        q = (base or Appointment.query)
        if staff: q = q.filter(Appointment.inviter == staff)
        return q
    def _txn_q(base=None):
        q = (base or Transaction.query)
        if staff: q = q.filter(Transaction.consultant == staff)
        return q
    def _pat_q(base=None):
        q = (base or Patient.query)
        if staff: q = q.filter(Patient.online_consultant == staff)
        return q

    # 今日预约数
    today_appointments = _appt_q().filter(
        Appointment.scheduled_date == today
    ).count()

    # 今日到访数
    today_visited = _appt_q().filter(
        Appointment.scheduled_date == today,
        Appointment.actual_visit.isnot(None),
        Appointment.actual_visit != '',
        Appointment.actual_visit != '未到访'
    ).count()

    # 本月成交额
    monthly_revenue = _txn_q(db.session.query(func.sum(Transaction.performance_amount))).filter(
        Transaction.payment_date >= month_start
    ).scalar() or 0

    # 本月成交数
    monthly_deals = _txn_q().filter(
        Transaction.payment_date >= month_start
    ).count()

    # 本月预约数
    monthly_appointments = _appt_q().filter(
        Appointment.scheduled_date >= month_start
    ).count()

    # 本月新增患者
    monthly_patients = _pat_q().filter(
        Patient.created_at >= datetime.combine(month_start, datetime.min.time())
    ).count()

    # 总患者数
    total_patients = _pat_q().count()

    # 待跟进（最近30天未成交的初诊）
    thirty_days_ago = today - timedelta(days=30)
    pending_followups = _appt_q().filter(
        Appointment.scheduled_date >= thirty_days_ago,
        Appointment.scheduled_date <= today,
        or_(
            Appointment.actual_visit == '未成交',
            Appointment.actual_visit == '',
            Appointment.actual_visit.is_(None)
        ),
        Appointment.visit_type == '初诊'
    ).count()

    # 本月业绩趋势（按天）
    import calendar
    days_in_month = calendar.monthrange(ref_date.year, ref_date.month)[1]
    days_to_show = days_in_month if ref_date != date.today() else min(days_in_month, today.day)
    revenue_trend = []
    for i in range(days_to_show):
        d = date(ref_date.year, ref_date.month, i + 1)
        day_total = _txn_q(db.session.query(func.sum(Transaction.performance_amount))).filter(
            Transaction.payment_date == d
        ).scalar() or 0
        revenue_trend.append({'date': d.strftime('%m-%d'), 'amount': float(day_total)})

    # 咨询师排名（本月）
    consultant_ranking = _txn_q(db.session.query(
        Transaction.consultant,
        func.sum(Transaction.performance_amount).label('total'),
        func.count(Transaction.id).label('count')
    )).filter(
        Transaction.payment_date >= month_start,
        Transaction.consultant.isnot(None),
        Transaction.consultant != ''
    ).group_by(Transaction.consultant).order_by(func.sum(Transaction.performance_amount).desc()).all()

    # 最近预约
    recent_appointments = _appt_q().filter(
        Appointment.scheduled_date >= today
    ).order_by(Appointment.scheduled_date).limit(8).all()

    # 最近成交
    recent_transactions = _txn_q().filter(
        Transaction.payment_date.isnot(None)
    ).order_by(Transaction.payment_date.desc()).limit(8).all()

    return jsonify({
        'today_appointments': today_appointments,
        'today_visited': today_visited,
        'monthly_revenue': float(monthly_revenue),
        'monthly_deals': monthly_deals,
        'monthly_appointments': monthly_appointments,
        'monthly_patients': monthly_patients,
        'total_patients': total_patients,
        'pending_followups': pending_followups,
        'revenue_trend': revenue_trend,
        'consultant_ranking': [
            {'name': r[0] or '未知', 'total': float(r[1] or 0), 'count': r[2]}
            for r in consultant_ranking
        ],
        'recent_appointments': [a.to_dict() for a in recent_appointments],
        'recent_transactions': [t.to_dict() for t in recent_transactions],
    })


# =================== 患者管理 ===================

@app.route('/patients')
def patients_page():
    return no_cache(render_template('base.html'))


@app.route('/api/patients')
def api_patients():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '').strip()
    filter_date = request.args.get('date', '').strip()

    query = Patient.query
    # Staff data isolation: only see own patients
    staff = _staff_name()
    if staff:
        query = query.filter(Patient.online_consultant == staff)
    if search:
        query = query.filter(
            or_(
                Patient.name.contains(search),
                Patient.phone.contains(search),
                Patient.internal_id.contains(search),
                Patient.online_consultant.contains(search)
            )
        )

    # 按预约日期筛选
    if filter_date:
        try:
            target_date = datetime.strptime(filter_date, '%Y-%m-%d').date()
            sub = db.session.query(Appointment.patient_id).filter(
                Appointment.scheduled_date == target_date
            ).subquery()
            query = query.filter(Patient.id.in_(sub))
        except ValueError:
            pass

    total = query.count()
    patients = query.order_by(Patient.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # 为每个患者附加最近一次预约信息
    result = []
    for p in patients.items:
        d = p.to_dict()
        # 获取该患者最新的预约
        latest_appt = Appointment.query.filter_by(patient_id=p.id).order_by(Appointment.scheduled_date.desc()).first()
        d['inviter'] = latest_appt.inviter if latest_appt else ''
        d['scheduled_date'] = latest_appt.scheduled_date.strftime('%Y-%m-%d') if (latest_appt and latest_appt.scheduled_date) else ''
        d['registered_date'] = latest_appt.registered_date.strftime('%Y-%m-%d') if (latest_appt and latest_appt.registered_date) else ''
        result.append(d)

    return jsonify({
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page,
        'data': result
    })


@app.route('/api/patients/<int:pid>')
def api_patient_detail(pid):
    patient = Patient.query.get_or_404(pid)
    # Staff data isolation: only see own patients
    staff = _staff_name()
    if staff and patient.online_consultant != staff:
        return jsonify({'error': 'forbidden', 'message': '权限不足'}), 403
    appointments = Appointment.query.filter_by(patient_id=pid).order_by(
        Appointment.scheduled_date.desc()
    ).all()
    transactions = Transaction.query.filter_by(patient_id=pid).order_by(
        Transaction.payment_date.desc()
    ).all()
    images = PatientImage.query.filter_by(patient_id=pid).order_by(
        PatientImage.stage, PatientImage.category, PatientImage.sub_type
    ).all()
    treatment_plans = TreatmentPlan.query.filter_by(patient_id=pid).order_by(
        TreatmentPlan.section, TreatmentPlan.sort_order
    ).all()
    return jsonify({
        'patient': patient.to_dict(),
        'appointments': [a.to_dict() for a in appointments],
        'transactions': [t.to_dict() for t in transactions],
        'images': [img.to_dict() for img in images],
        'treatment_plans': [tp.to_dict() for tp in treatment_plans],
    })


@app.route('/api/patients', methods=['POST'])
def api_create_patient():
    data = request.get_json()
    phone = normalize_phone(data.get('phone', '')) or None

    # 按电话号码查找重复患者
    existing = None
    if phone:
        existing = Patient.query.filter_by(phone=phone).first()
    if not existing:
        internal_id = data.get('internal_id', '').strip()
        if internal_id:
            existing = Patient.query.filter_by(internal_id=internal_id).first()

    if existing:
        # 合并：更新现有患者的信息
        for field in ['name', 'gender', 'tooth_count', 'condition_desc',
                      'source', 'source_channel', 'online_consultant']:
            val = data.get(field)
            if val:
                setattr(existing, field, val)
        if 'age' in data and data['age']:
            existing.age = int(data['age'])
        existing.updated_at = datetime.now()
        db.session.commit()
        sse_broadcast('patient_updated', existing.to_dict())
        return jsonify({'success': True, 'merged': True, 'data': existing.to_dict()})

    # 自动生成内部编号
    internal_id = data.get('internal_id', '').strip()
    if not internal_id:
        last = Patient.query.order_by(Patient.id.desc()).first()
        next_num = (last.id + 1) if last else 1
        internal_id = f'MEYA-{next_num:04d}'

    p = Patient(
        internal_id=internal_id,
        name=data.get('name', ''),
        phone=phone,
        gender=data.get('gender', ''),
        age=data.get('age', 0),
        tooth_count=data.get('tooth_count', ''),
        condition_desc=data.get('condition_desc', ''),
        source=data.get('source', ''),
        source_channel=data.get('source_channel', ''),
        online_consultant=data.get('online_consultant', ''),
    )
    db.session.add(p)
    db.session.commit()
    sse_broadcast('patient_created', p.to_dict())
    return jsonify({'success': True, 'merged': False, 'data': p.to_dict()})


@app.route('/api/patients/<int:pid>', methods=['PUT'])
def api_update_patient(pid):
    p = Patient.query.get_or_404(pid)
    data = request.get_json()
    for field in ['name', 'phone', 'gender', 'tooth_count', 'condition_desc',
                  'source', 'source_channel', 'online_consultant', 'internal_id']:
        if field in data:
            setattr(p, field, data[field])
    if 'age' in data and data['age']:
        p.age = int(data['age'])
    p.updated_at = datetime.now()
    db.session.commit()
    sse_broadcast('patient_updated', p.to_dict())
    return jsonify({'success': True, 'data': p.to_dict()})


@app.route('/api/patients/<int:pid>', methods=['DELETE'])
def api_delete_patient(pid):
    p = Patient.query.get_or_404(pid)
    db.session.delete(p)
    db.session.commit()
    sse_broadcast('patient_deleted', {'id': pid})
    return jsonify({'success': True})


# =================== 治疗方案 ===================

@app.route('/api/patients/<int:pid>/treatment-plans')
def api_get_treatment_plans(pid):
    perms = flask_session.get('permissions', {})
    if not perms.get('is_admin') and not perms.get('can_view_treatment_plans'):
        return jsonify({'error': 'forbidden', 'message': '权限不足'}), 403
    plans = TreatmentPlan.query.filter_by(patient_id=pid).order_by(
        TreatmentPlan.section, TreatmentPlan.sort_order
    ).all()
    return jsonify({'data': [tp.to_dict() for tp in plans]})


@app.route('/api/patients/<int:pid>/treatment-plans', methods=['POST'])
def api_create_treatment_plan(pid):
    perms = flask_session.get('permissions', {})
    if not perms.get('is_admin') and not perms.get('can_view_treatment_plans'):
        return jsonify({'error': 'forbidden', 'message': '权限不足'}), 403
    data = request.get_json()
    tp = TreatmentPlan(
        patient_id=pid,
        section=data.get('section', '检查'),
        batch=data.get('batch', ''),
        tooth_mark=data.get('tooth_mark', ''),
        note=data.get('note', ''),
        sort_order=data.get('sort_order', 0),
    )
    db.session.add(tp)
    db.session.commit()
    return jsonify({'success': True, 'data': tp.to_dict()})


@app.route('/api/treatment-plans/<int:tid>', methods=['PUT'])
def api_update_treatment_plan(tid):
    tp = TreatmentPlan.query.get_or_404(tid)
    data = request.get_json()
    for field in ['section', 'batch', 'tooth_mark', 'note', 'sort_order']:
        if field in data:
            setattr(tp, field, data[field])
    db.session.commit()
    return jsonify({'success': True, 'data': tp.to_dict()})


@app.route('/api/treatment-plans/<int:tid>', methods=['DELETE'])
def api_delete_treatment_plan(tid):
    tp = TreatmentPlan.query.get_or_404(tid)
    db.session.delete(tp)
    db.session.commit()
    return jsonify({'success': True})


# =================== 费用明细 ===================

@app.route('/api/treatment-plans/<int:tid>/cost-items')
def api_get_cost_items(tid):
    """获取某个治疗方案的费用明细"""
    items = CostItem.query.filter_by(treatment_plan_id=tid).order_by(
        CostItem.sort_order
    ).all()
    return jsonify({'data': [item.to_dict() for item in items]})


@app.route('/api/treatment-plans/<int:tid>/cost-items', methods=['POST'])
def api_create_cost_item(tid):
    """为治疗方案添加费用项"""
    data = request.get_json()
    ci = CostItem(
        treatment_plan_id=tid,
        major_category=data.get('major_category', ''),
        sub_category=data.get('sub_category', ''),
        unit_price=float(data.get('unit_price', 0) or 0),
        quantity=int(data.get('quantity', 1) or 1),
        discount_rate=float(data.get('discount_rate', 0) or 0),
        total_price=float(data.get('total_price', 0) or 0),
        sort_order=data.get('sort_order', 0),
    )
    db.session.add(ci)
    db.session.commit()
    return jsonify({'success': True, 'data': ci.to_dict()})


@app.route('/api/cost-items/<int:cid>', methods=['PUT'])
def api_update_cost_item(cid):
    """更新费用项"""
    ci = CostItem.query.get_or_404(cid)
    data = request.get_json()
    for field in ['major_category', 'sub_category']:
        if field in data:
            setattr(ci, field, data[field])
    for field in ['unit_price', 'discount_rate', 'total_price']:
        if field in data:
            setattr(ci, field, float(data[field] or 0))
    if 'quantity' in data:
        ci.quantity = int(data['quantity'] or 1)
    if 'sort_order' in data:
        ci.sort_order = data['sort_order']
    db.session.commit()
    return jsonify({'success': True, 'data': ci.to_dict()})


@app.route('/api/cost-items/<int:cid>', methods=['DELETE'])
def api_delete_cost_item(cid):
    """删除费用项"""
    ci = CostItem.query.get_or_404(cid)
    db.session.delete(ci)
    db.session.commit()
    return jsonify({'success': True})


# =================== 业绩管理 ===================

@app.route('/api/performance')
def api_performance():
    perms = flask_session.get('permissions', {})
    if not perms.get('is_admin') and not perms.get('can_view_performance'):
        return jsonify({'error': 'forbidden', 'message': '权限不足'}), 403

    year = request.args.get('year', date.today().year, type=int)
    month = request.args.get('month', date.today().month, type=int)
    month_start = date(year, month, 1)
    if month == 12:
        month_end = date(year + 1, 1, 1)
    else:
        month_end = date(year, month + 1, 1)

    staff = _staff_name()

    # 网咨人员业绩 (通过患者表的 online_consultant 关联成交记录)
    online_rows = db.session.query(
        Patient.online_consultant,
        func.sum(Transaction.performance_amount).label('total'),
        func.count(Transaction.id).label('count')
    ).join(Transaction, Transaction.patient_id == Patient.id).filter(
        Transaction.payment_date >= month_start,
        Transaction.payment_date < month_end,
        Patient.online_consultant.isnot(None),
        Patient.online_consultant != ''
    )
    if staff:
        online_rows = online_rows.filter(Patient.online_consultant == staff)
    online_rows = online_rows.group_by(Patient.online_consultant).order_by(func.sum(Transaction.performance_amount).desc()).all()

    # 咨询师业绩 (直接从成交记录)
    consultant_rows = db.session.query(
        Transaction.consultant,
        func.sum(Transaction.performance_amount).label('total'),
        func.count(Transaction.id).label('count')
    ).filter(
        Transaction.payment_date >= month_start,
        Transaction.payment_date < month_end,
        Transaction.consultant.isnot(None),
        Transaction.consultant != ''
    )
    if staff:
        consultant_rows = consultant_rows.filter(Transaction.consultant == staff)
    consultant_rows = consultant_rows.group_by(Transaction.consultant).order_by(func.sum(Transaction.performance_amount).desc()).all()

    # 合计
    total_online = sum(r[1] or 0 for r in online_rows)
    total_consultant = sum(r[1] or 0 for r in consultant_rows)

    # 按咨询师的明细列表（供折叠详情用）
    detail_rows = db.session.query(
        Transaction.consultant,
        Patient.name,
        Patient.online_consultant,
        Transaction.performance_amount,
        Transaction.payment_date,
        Transaction.plan_type
    ).join(Patient, Transaction.patient_id == Patient.id).filter(
        Transaction.payment_date >= month_start,
        Transaction.payment_date < month_end,
        Transaction.consultant.isnot(None),
        Transaction.consultant != ''
    )
    if staff:
        detail_rows = detail_rows.filter(Transaction.consultant == staff)
    detail_rows = detail_rows.order_by(Transaction.payment_date.desc()).all()

    return jsonify({
        'year': year,
        'month': month,
        'online_consultants': [
            {'name': r[0] or '未知', 'total': float(r[1] or 0), 'count': r[2]}
            for r in online_rows
        ],
        'consultants': [
            {'name': r[0] or '未知', 'total': float(r[1] or 0), 'count': r[2]}
            for r in consultant_rows
        ],
        'total_online': float(total_online),
        'total_consultant': float(total_consultant),
        'details': [
            {
                'consultant': r[0] or '',
                'patient_name': r[1] or '',
                'online_consultant': r[2] or '',
                'amount': float(r[3] or 0),
                'date': r[4].strftime('%Y-%m-%d') if r[4] else '',
                'plan': r[5] or '',
            }
            for r in detail_rows
        ],
    })


def _check_permission(perm_key):
    """Check if current user has a specific permission. Returns JSON error or None."""
    perms = flask_session.get('permissions', {})
    if perms.get('is_admin'):
        return None
    if not perms.get(perm_key):
        return jsonify({'error': 'forbidden', 'message': '权限不足'}), 403
    return None


def _staff_name():
    """Return the current staff member's display name for data isolation.
    Only 网咨人员 (online_consultant) get data isolation.
    门诊人员 (clinic_staff) and admin see all data."""
    if flask_session.get('permissions', {}).get('is_admin'):
        return None
    emp_type = flask_session.get('employee_type', '')
    if emp_type == 'clinic_staff':
        return None  # 门诊人员 sees all
    return flask_session.get('display_name', '')  # 网咨人员 sees own only


def _apply_staff_filter(query, model_class, field):
    """If current user is non-admin staff, filter query to own records only."""
    name = _staff_name()
    if not name:
        return query
    # Build column reference dynamically
    col = getattr(model_class, field)
    return query.filter(col == name)


@app.route('/performance')
def performance_page():
    return no_cache(render_template('base.html'))


# =================== 预约管理 ===================

@app.route('/appointments')
def appointments_page():
    return no_cache(render_template('base.html'))

@app.route('/followups')
def followups_page():
    return no_cache(render_template('base.html'))


@app.route('/api/appointments')
def api_appointments():
    perms = flask_session.get('permissions', {})
    if not perms.get('is_admin') and not perms.get('can_view_appointments'):
        return jsonify({'error': 'forbidden', 'message': '权限不足'}), 403
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status', '')
    search = request.args.get('search', '').strip()
    month = request.args.get('month', '')

    visit_type = request.args.get('visit_type', '初诊')  # default to 初诊 for backward compat
    query = Appointment.query.filter(Appointment.visit_type == visit_type)
    # Staff data isolation: only see own appointments
    staff = _staff_name()
    if staff:
        query = query.filter(Appointment.inviter == staff)

    if search:
        query = query.join(Patient).filter(
            or_(
                Patient.name.contains(search),
                Patient.phone.contains(search),
                Patient.internal_id.contains(search),
                Appointment.inviter.contains(search),
                Appointment.phone.contains(search),
            )
        )

    if status == 'today':
        query = query.filter(Appointment.scheduled_date == date.today())
    elif status == 'upcoming':
        query = query.filter(Appointment.scheduled_date >= date.today())
    elif status == 'past':
        query = query.filter(Appointment.scheduled_date < date.today())
    elif status == 'visited':
        query = query.filter(
            Appointment.actual_visit.isnot(None),
            Appointment.actual_visit != '',
            Appointment.actual_visit != '未到访'
        )
    elif status == 'noshow':
        query = query.filter(Appointment.actual_visit == '未到访')
    elif status == 'nodata':
        query = query.filter(
            or_(
                Appointment.actual_visit.is_(None),
                Appointment.actual_visit == ''
            )
        )
    elif status == 'deals':
        query = query.filter(
            Appointment.actual_visit.in_(['成交', '定金', '定金转成交', '未成交转成交'])
        )

    if month:
        try:
            y, m = month.split('-')
            query = query.filter(
                extract('year', Appointment.scheduled_date) == int(y),
                extract('month', Appointment.scheduled_date) == int(m)
            )
        except:
            pass

    total = query.count()
    appointments = query.order_by(Appointment.scheduled_date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page,
        'data': [a.to_dict() for a in appointments.items]
    })


@app.route('/api/appointments', methods=['POST'])
def api_create_appointment():
    data = request.get_json()
    patient_id = data.get('patient_id')

    # 如果没传 patient_id，按电话/内部编号/姓名查找或创建患者
    if not patient_id:
        phone = normalize_phone(data.get('phone', '')) or None
        internal_id = data.get('internal_id', '').strip()
        name = data.get('patient_name', '').strip()

        patient = None
        if phone:
            patient = Patient.query.filter_by(phone=phone).first()
        if not patient and internal_id:
            patient = Patient.query.filter_by(internal_id=internal_id).first()
        if not patient and name:
            patient = Patient.query.filter_by(name=name).first()

        if not patient:
            if not phone and not internal_id and not name:
                return jsonify({'success': False, 'error': '请提供患者信息（姓名/电话/编号）'}), 400
            last = Patient.query.order_by(Patient.id.desc()).first()
            next_num = (last.id + 1) if last else 1
            internal_id = internal_id or f'MEYA-{next_num:04d}'
            patient = Patient(internal_id=internal_id, name=name, phone=phone)
            db.session.add(patient)
            db.session.flush()
        patient_id = patient.id

    a = Appointment(
        patient_id=patient_id,
        scheduled_date=_parse_date(data.get('scheduled_date')),
        scheduled_time=data.get('scheduled_time', ''),
        inviter=data.get('inviter', ''),
        inviter_2=data.get('inviter_2', ''),
        phone=normalize_phone(data.get('phone', '')),
        visit_type=data.get('visit_type', ''),
        actual_visit=data.get('actual_visit', ''),
        consultation_notes=data.get('consultation_notes', ''),
        followup_24h=data.get('followup_24h', ''),
        followup_7d=data.get('followup_7d', ''),
        followup_15d=data.get('followup_15d', ''),
        followup_30d=data.get('followup_30d', ''),
        need_collab=data.get('need_collab', ''),
        invalid_reason=data.get('invalid_reason', ''),
        has_continue=data.get('has_continue', ''),
        registered_date=_parse_date(data.get('registered_date')),
        doctor=data.get('doctor', ''),
        treatment_project=data.get('treatment_project', ''),
        total_fee=float(data.get('total_fee', 0) or 0),
        paid_fee=float(data.get('paid_fee', 0) or 0),
    )
    db.session.add(a)
    db.session.commit()
    sse_broadcast('appointment_created', a.to_dict())
    return jsonify({'success': True, 'data': a.to_dict()})


@app.route('/api/appointments/<int:aid>')
def api_get_appointment(aid):
    """Get a single appointment by ID."""
    a = Appointment.query.get_or_404(aid)
    return jsonify({'success': True, 'data': a.to_dict()})


@app.route('/api/appointments/<int:aid>', methods=['PUT'])
def api_update_appointment(aid):
    a = Appointment.query.get_or_404(aid)
    data = request.get_json()
    for field in ['scheduled_time', 'inviter', 'inviter_2', 'phone', 'visit_type',
                  'actual_visit', 'consultation_notes', 'followup_24h', 'followup_7d',
                  'followup_15d', 'followup_30d', 'need_collab', 'invalid_reason',
                  'has_continue', 'doctor', 'treatment_project']:
        if field in data:
            setattr(a, field, data[field])
    for field in ['total_fee', 'paid_fee']:
        if field in data:
            setattr(a, field, float(data[field] or 0))
    if 'scheduled_date' in data:
        a.scheduled_date = _parse_date(data['scheduled_date'])
    if 'registered_date' in data:
        a.registered_date = _parse_date(data['registered_date'])
    if 'patient_id' in data and data['patient_id']:
        a.patient_id = data['patient_id']
    db.session.commit()
    sse_broadcast('appointment_updated', a.to_dict())
    return jsonify({'success': True, 'data': a.to_dict()})


@app.route('/api/appointments/<int:aid>', methods=['DELETE'])
def api_delete_appointment(aid):
    a = Appointment.query.get_or_404(aid)
    db.session.delete(a)
    db.session.commit()
    sse_broadcast('appointment_deleted', {'id': aid})
    return jsonify({'success': True})


# =================== 成交管理 ===================

@app.route('/transactions')
def transactions_page():
    return no_cache(render_template('base.html'))


@app.route('/api/transactions')
def api_transactions():
    perms = flask_session.get('permissions', {})
    if not perms.get('is_admin') and not perms.get('can_view_transactions'):
        return jsonify({'error': 'forbidden', 'message': '权限不足'}), 403
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '').strip()
    month = request.args.get('month', '')

    query = Transaction.query
    # Staff data isolation: only see own transactions
    staff = _staff_name()
    if staff:
        query = query.filter(Transaction.consultant == staff)

    if search:
        query = query.join(Patient).filter(
            or_(
                Patient.name.contains(search),
                Transaction.consultant.contains(search),
                Transaction.plan_type.contains(search),
            )
        )

    if month:
        try:
            y, m = month.split('-')
            query = query.filter(
                extract('year', Transaction.payment_date) == int(y),
                extract('month', Transaction.payment_date) == int(m)
            )
        except:
            pass

    total = query.count()
    transactions = query.order_by(Transaction.payment_date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page,
        'data': [t.to_dict() for t in transactions.items]
    })


@app.route('/api/transactions', methods=['POST'])
def api_create_transaction():
    data = request.get_json()
    patient_id = data.get('patient_id')

    if not patient_id:
        phone = normalize_phone(data.get('phone', '')) or None
        internal_id = data.get('internal_id', '').strip()
        name = data.get('patient_name', '').strip()

        # 优先按电话号码查找，其次内部编号，最后姓名
        patient = None
        if phone:
            patient = Patient.query.filter_by(phone=phone).first()
        if not patient and internal_id:
            patient = Patient.query.filter_by(internal_id=internal_id).first()
        if not patient and name:
            patient = Patient.query.filter_by(name=name).first()

        if not patient:
            # 无任何标识信息，无法创建患者
            if not phone and not internal_id and not name:
                return jsonify({'success': False, 'error': '请提供患者信息（姓名/电话/编号）'}), 400
            # 自动生成内部编号
            last = Patient.query.order_by(Patient.id.desc()).first()
            next_num = (last.id + 1) if last else 1
            internal_id = internal_id or f'MEYA-{next_num:04d}'
            patient = Patient(
                internal_id=internal_id,
                name=name,
                phone=phone,
            )
            db.session.add(patient)
            db.session.flush()
        patient_id = patient.id

    t = Transaction(
        patient_id=patient_id,
        plan_type=data.get('plan_type', ''),
        plan_detail=data.get('plan_detail', ''),
        brand=data.get('brand', ''),
        tooth_positions=data.get('tooth_positions', ''),
        tooth_count=data.get('tooth_count', 0),
        bone_graft=data.get('bone_graft', ''),
        bone_membrane=data.get('bone_membrane', ''),
        sinus_lift=data.get('sinus_lift', ''),
        deposit_amount=float(data.get('deposit_amount', 0) or 0),
        deposit_contract=float(data.get('deposit_contract', 0) or 0),
        deposit_date=_parse_date(data.get('deposit_date')),
        deposit_return_date=_parse_date(data.get('deposit_return_date')),
        performance_amount=float(data.get('performance_amount', 0) or 0),
        paid_amount=float(data.get('paid_amount', 0) or 0),
        payment_date=_parse_date(data.get('payment_date')),
        total_amount=float(data.get('total_amount', 0) or 0),
        payment=float(data.get('payment', 0) or 0),
        payment_date_2=_parse_date(data.get('payment_date_2')),
        supplement_amount=float(data.get('supplement_amount', 0) or 0),
        supplement_date=_parse_date(data.get('supplement_date')),
        debt_amount=float(data.get('debt_amount', 0) or 0),
        supplement_records=data.get('supplement_records', ''),
        treatment_date=_parse_date(data.get('treatment_date')),
        treatment_doctor=data.get('treatment_doctor', ''),
        visit_outcome=data.get('visit_outcome', ''),
        consultant=data.get('consultant', ''),
    )
    db.session.add(t)
    db.session.commit()
    sse_broadcast('transaction_created', t.to_dict())
    return jsonify({'success': True, 'data': t.to_dict()})


@app.route('/api/transactions/<int:tid>', methods=['PUT'])
def api_update_transaction(tid):
    t = Transaction.query.get_or_404(tid)
    data = request.get_json()
    for field in ['plan_type', 'plan_detail', 'brand', 'tooth_positions',
                  'bone_graft', 'bone_membrane', 'sinus_lift', 'supplement_records',
                  'treatment_doctor', 'visit_outcome', 'consultant']:
        if field in data:
            setattr(t, field, data[field])
    for num_field in ['tooth_count', 'deposit_amount', 'deposit_contract',
                      'performance_amount', 'paid_amount', 'total_amount', 'payment',
                      'supplement_amount', 'debt_amount']:
        if num_field in data:
            setattr(t, num_field, float(data[num_field] or 0))
    for date_field in ['deposit_date', 'deposit_return_date', 'payment_date',
                       'payment_date_2', 'supplement_date', 'treatment_date']:
        if date_field in data:
            setattr(t, date_field, _parse_date(data[date_field]))
    if 'patient_id' in data and data['patient_id']:
        t.patient_id = data['patient_id']
    db.session.commit()
    sse_broadcast('transaction_updated', t.to_dict())
    return jsonify({'success': True, 'data': t.to_dict()})


@app.route('/api/transactions/<int:tid>', methods=['DELETE'])
def api_delete_transaction(tid):
    t = Transaction.query.get_or_404(tid)
    db.session.delete(t)
    db.session.commit()
    sse_broadcast('transaction_deleted', {'id': tid})
    return jsonify({'success': True})


# =================== 报表 ===================

@app.route('/reports')
def reports_page():
    return no_cache(render_template('base.html'))


@app.route('/api/reports/monthly')
def api_reports_monthly():
    """月度明细报表 - 每日预约/成交/收款 + 网咨统计"""
    perms = flask_session.get('permissions', {})
    if not perms.get('is_admin') and not perms.get('can_view_reports'):
        return jsonify({'error': 'forbidden', 'message': '权限不足'}), 403
    
    year = request.args.get('year', date.today().year, type=int)
    month = request.args.get('month', date.today().month, type=int)
    
    import calendar
    days_in_month = calendar.monthrange(year, month)[1]
    staff = _staff_name()
    
    # 1. 每日预约数量
    daily_appointments = []
    for d in range(1, days_in_month + 1):
        target = date(year, month, d)
        q = Appointment.query.filter(Appointment.scheduled_date == target)
        if staff: q = q.filter(Appointment.inviter == staff)
        cnt = q.count()
        daily_appointments.append({'date': f'{month}/{d}', 'count': cnt})
    
    # 2. 每日成交金额
    daily_revenue = []
    for d in range(1, days_in_month + 1):
        target = date(year, month, d)
        q = db.session.query(func.sum(Transaction.performance_amount)).filter(
            Transaction.payment_date == target
        )
        if staff: q = q.filter(Transaction.consultant == staff)
        total = q.scalar() or 0
        daily_revenue.append({'date': f'{month}/{d}', 'amount': float(total)})
    
    # 3. 网咨人员预约数量 (按 inviter)
    inviter_appointments = db.session.query(
        Appointment.inviter,
        func.count(Appointment.id)
    ).filter(
        extract('year', Appointment.scheduled_date) == year,
        extract('month', Appointment.scheduled_date) == month,
        Appointment.inviter.isnot(None),
        Appointment.inviter != ''
    )
    if staff: inviter_appointments = inviter_appointments.filter(Appointment.inviter == staff)
    inviter_appointments = inviter_appointments.group_by(Appointment.inviter).order_by(func.count(Appointment.id).desc()).all()
    
    # 4. 网咨人员成交金额 (按患者表的 online_consultant)
    consultant_revenue = db.session.query(
        Patient.online_consultant,
        func.sum(Transaction.performance_amount).label('total'),
        func.count(Transaction.id).label('count')
    ).join(Transaction, Transaction.patient_id == Patient.id).filter(
        extract('year', Transaction.payment_date) == year,
        extract('month', Transaction.payment_date) == month,
        Patient.online_consultant.isnot(None),
        Patient.online_consultant != ''
    )
    if staff: consultant_revenue = consultant_revenue.filter(Patient.online_consultant == staff)
    consultant_revenue = consultant_revenue.group_by(Patient.online_consultant).order_by(func.sum(Transaction.performance_amount).desc()).all()
    
    # 5. 每日收款金额 (paid_amount)
    daily_collection = []
    for d in range(1, days_in_month + 1):
        target = date(year, month, d)
        q = db.session.query(func.sum(Transaction.paid_amount)).filter(
            Transaction.payment_date == target
        )
        if staff: q = q.filter(Transaction.consultant == staff)
        total = q.scalar() or 0
        daily_collection.append({'date': f'{month}/{d}', 'amount': float(total)})
    
    return jsonify({
        'year': year,
        'month': month,
        'days_in_month': days_in_month,
        'daily_appointments': daily_appointments,
        'daily_revenue': daily_revenue,
        'daily_collection': daily_collection,
        'inviter_appointments': [{'name': r[0], 'count': r[1]} for r in inviter_appointments],
        'consultant_revenue': [{'name': r[0], 'total': float(r[1] or 0), 'count': r[2]} for r in consultant_revenue],
    })


@app.route('/api/reports/overview')
def api_reports_overview():
    perms = flask_session.get('permissions', {})
    if not perms.get('is_admin') and not perms.get('can_view_reports'):
        return jsonify({'error': 'forbidden', 'message': '权限不足'}), 403
    year = request.args.get('year', date.today().year, type=int)
    staff = _staff_name()

    # 月度业绩
    monthly_revenue = []
    for m in range(1, 13):
        q = db.session.query(func.sum(Transaction.performance_amount)).filter(
            extract('year', Transaction.payment_date) == year,
            extract('month', Transaction.payment_date) == m
        )
        if staff: q = q.filter(Transaction.consultant == staff)
        total = q.scalar() or 0
        monthly_revenue.append({'month': f'{m}月', 'amount': float(total)})

    # 咨询师年度排名
    consultant_ranking = db.session.query(
        Transaction.consultant,
        func.sum(Transaction.performance_amount).label('total'),
        func.count(Transaction.id).label('count')
    ).filter(
        extract('year', Transaction.payment_date) == year,
        Transaction.consultant.isnot(None),
        Transaction.consultant != ''
    )
    if staff: consultant_ranking = consultant_ranking.filter(Transaction.consultant == staff)
    consultant_ranking = consultant_ranking.group_by(Transaction.consultant).order_by(
        func.sum(Transaction.performance_amount).desc()
    ).all()

    # 来源分析
    source_analysis = db.session.query(
        Patient.source,
        func.count(Patient.id)
    )
    if staff: source_analysis = source_analysis.filter(Patient.online_consultant == staff)
    source_analysis = source_analysis.filter(
        Patient.source.isnot(None),
        Patient.source != ''
    ).group_by(Patient.source).all()

    # 到访情况分析
    visit_analysis = db.session.query(
        Appointment.actual_visit,
        func.count(Appointment.id)
    )
    if staff: visit_analysis = visit_analysis.filter(Appointment.inviter == staff)
    visit_analysis = visit_analysis.filter(
        Appointment.actual_visit.isnot(None),
        Appointment.actual_visit != ''
    ).group_by(Appointment.actual_visit).all()

    return jsonify({
        'monthly_revenue': monthly_revenue,
        'consultant_ranking': [
            {'name': r[0], 'total': float(r[1] or 0), 'count': r[2]}
            for r in consultant_ranking
        ],
        'source_analysis': [
            {'name': r[0], 'count': r[1]} for r in source_analysis
        ],
        'visit_analysis': [
            {'name': r[0], 'count': r[1]} for r in visit_analysis
        ],
    })


# =================== SSE 实时推送 ===================

@app.route('/api/events')
def sse_events():
    from queue import Queue
    q = Queue()
    sse_clients.append(q)

    def stream():
        try:
            yield 'event: connected\ndata: {}\n\n'
            while True:
                msg = q.get()
                yield msg
        except GeneratorExit:
            if q in sse_clients:
                sse_clients.remove(q)

    return Response(stream(), mimetype='text/event-stream')


# =================== Debug ===================

# =================== 患者图片管理 ===================

# 上传目录
IMAGE_UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads', 'images')
os.makedirs(IMAGE_UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/patient-images')
def patient_images_page():
    return no_cache(render_template('base.html'))

@app.route('/treatment-plans')
def treatment_plans_page():
    return no_cache(render_template('base.html'))


@app.route('/api/images/<filename>')
def serve_image(filename):
    """Serve uploaded patient images."""
    filepath = os.path.join(IMAGE_UPLOAD_DIR, filename)
    if not os.path.exists(filepath):
        return '', 404
    return send_from_directory(IMAGE_UPLOAD_DIR, filename)


@app.route('/api/patients/<int:pid>/images')
def api_get_patient_images(pid):
    """Get all images for a patient, grouped by stage/category."""
    perms = flask_session.get('permissions', {})
    if not perms.get('is_admin') and not perms.get('can_view_images'):
        return jsonify({'error': 'forbidden', 'message': '权限不足'}), 403
    images = PatientImage.query.filter_by(patient_id=pid).order_by(
        PatientImage.stage, PatientImage.category, PatientImage.sub_type, PatientImage.position
    ).all()
    return jsonify({'data': [img.to_dict() for img in images]})


@app.route('/api/patients/<int:pid>/images', methods=['POST'])
def api_upload_patient_image(pid):
    """Upload an image for a patient."""
    perms = flask_session.get('permissions', {})
    if not perms.get('is_admin') and not perms.get('can_view_images'):
        return jsonify({'error': 'forbidden', 'message': '权限不足'}), 403
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': '未选择文件'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': '文件名为空'}), 400

    if not allowed_file(file.filename):
        return jsonify({'success': False, 'error': '不支持的文件格式'}), 400

    stage = request.form.get('stage', '术前')
    category = request.form.get('category', '口内照')
    sub_type = request.form.get('sub_type', '')

    ext = file.filename.rsplit('.', 1)[1].lower()
    save_name = f"{uuid.uuid4().hex}.{ext}"
    save_path = os.path.join(IMAGE_UPLOAD_DIR, save_name)
    file.save(save_path)

    # 同位置已有图片数量（决定 position）
    existing_count = PatientImage.query.filter_by(
        patient_id=pid, stage=stage, category=category, sub_type=sub_type
    ).count()

    img = PatientImage(
        patient_id=pid,
        stage=stage,
        category=category,
        sub_type=sub_type,
        filename=save_name,
        original_name=file.filename,
        position=existing_count,
    )
    db.session.add(img)
    db.session.commit()

    return jsonify({'success': True, 'data': img.to_dict()})


@app.route('/api/images/<int:iid>', methods=['DELETE'])
def api_delete_patient_image(iid):
    """Delete a patient image."""
    img = PatientImage.query.get_or_404(iid)
    filepath = os.path.join(IMAGE_UPLOAD_DIR, img.filename)
    if os.path.exists(filepath):
        os.remove(filepath)
    db.session.delete(img)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/patients/images-summary')
def api_patient_images_summary():
    """Get patients with pre-op/post-op image counts, filtered by appointment date."""
    perms = flask_session.get('permissions', {})
    if not perms.get('is_admin') and not perms.get('can_view_images'):
        return jsonify({'error': 'forbidden', 'message': '权限不足'}), 403
    from sqlalchemy import func, case, text
    from datetime import date, timedelta
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '').strip()
    tomorrow = date.today() + timedelta(days=1)
    staff = _staff_name()
    
    # Subquery: latest appointment date per patient (only dates <= tomorrow)
    latest_appt = db.session.query(
        Appointment.patient_id,
        func.max(Appointment.scheduled_date).label('latest_date')
    ).filter(Appointment.scheduled_date <= tomorrow)\
    .group_by(Appointment.patient_id).subquery()
    
    # Base query: patients + image counts + latest appointment date
    base_q = db.session.query(
        Patient.id,
        Patient.name,
        Patient.phone,
        func.sum(case((PatientImage.stage == '术前', 1), else_=0)).label('pre_count'),
        func.sum(case((PatientImage.stage == '术后', 1), else_=0)).label('post_count'),
        latest_appt.c.latest_date
    ).outerjoin(PatientImage, Patient.id == PatientImage.patient_id)\
    .outerjoin(latest_appt, Patient.id == latest_appt.c.patient_id)
    
    # Filter by staff (own patients) or by appointment schedule
    if staff:
        staff_patient_ids = db.session.query(Appointment.patient_id).filter(
            Appointment.inviter == staff
        ).distinct()
        base_q = base_q.filter(
            or_(
                Patient.online_consultant == staff,
                Patient.id.in_(staff_patient_ids)
            )
        )
    else:
        base_q = base_q.filter(
            or_(
                latest_appt.c.latest_date.isnot(None),
                ~Patient.id.in_(
                    db.session.query(Appointment.patient_id).filter(Appointment.scheduled_date > tomorrow)
                )
            )
        )
    base_q = base_q.group_by(Patient.id, latest_appt.c.latest_date)
    
    if search:
        base_q = base_q.having(
            func.lower(Patient.name).contains(search.lower()) | 
            Patient.phone.contains(search)
        )
    
    total = base_q.count()
    
    rows = base_q\
        .order_by(latest_appt.c.latest_date.desc().nullslast(), Patient.name)\
        .offset((page - 1) * per_page)\
        .limit(per_page)\
        .all()
    
    result = []
    for r in rows:
        result.append({
            'id': r.id,
            'name': r.name,
            'phone': r.phone or '',
            'pre_count': r.pre_count or 0,
            'post_count': r.post_count or 0,
            'latest_appointment': r.latest_date.strftime('%Y-%m-%d') if r.latest_date else '',
        })
    return jsonify({'data': result, 'total': total, 'page': page, 'per_page': per_page})


# =================== Debug ===================

@app.route('/api/debug/employees')
def api_debug_employees():
    """Debug: check employees table."""
    import traceback, sys
    try:
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        
        # Try to fix tables
        db.create_all()
        
        err_msg = None
        emp_count = -1
        try:
            emp_count = Employee.query.count()
        except Exception as e2:
            err_msg = str(e2)
        
        return jsonify({
            'tables': tables,
            'employee_table_exists': 'employees' in tables,
            'employee_count': emp_count,
            'error': err_msg,
            'permissions': flask_session.get('permissions', {}),
            'role': flask_session.get('user_role', ''),
        })
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


# =================== 搜索补全 ===================

@app.route('/api/search/patients')
def api_search_patients():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])
    results = Patient.query.filter(
        or_(
            Patient.name.contains(q),
            Patient.phone.contains(q),
            Patient.internal_id.contains(q),
        )
    ).limit(10).all()
    return jsonify([{
        'id': p.id, 'name': p.name, 'phone': p.phone or '',
        'internal_id': p.internal_id or ''
    } for p in results])


# =================== 工具函数 ===================

def _parse_date(s):
    if not s or s == '':
        return None
    if isinstance(s, date) and not isinstance(s, datetime):
        return s
    if isinstance(s, datetime):
        return s.date()
    s = str(s).strip()
    for fmt in ['%Y-%m-%d', '%Y年%m月%d日', '%Y/%m/%d', '%m月%d日', '%d/%m/%Y']:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    # Handle formats like "5.31"
    import re
    m = re.match(r'(\d+)\.(\d+)', s)
    if m:
        try:
            return date(2026, int(m.group(1)), int(m.group(2)))
        except:
            pass
    return None

# =================== Lazy Initialization ===================
# Instead of running at module load (which blocks gunicorn startup),
# we initialize on the first request. This eliminates 502 errors.

_app_initialized = False
_init_error = None

def ensure_initialized():
    """Run on first request. Creates tables + imports if needed."""
    global _app_initialized, _init_error
    if _app_initialized:
        return True
    
    try:
        from sqlalchemy import text as sa_text
        
        # Try WAL mode; non-fatal if locked (database works without it)
        try:
            db.session.execute(sa_text('PRAGMA journal_mode=WAL'))
            db.session.execute(sa_text('PRAGMA synchronous=NORMAL'))
            db.session.commit()
        except Exception:
            db.session.rollback()
        
        # Create employees table if not exists
        try:
            db.session.execute(sa_text('''
                CREATE TABLE IF NOT EXISTS employees (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username VARCHAR(50) NOT NULL UNIQUE,
                    password VARCHAR(200) NOT NULL,
                    display_name VARCHAR(50) DEFAULT '',
                    role VARCHAR(20) DEFAULT 'staff',
                    can_view_appointments BOOLEAN DEFAULT 1,
                    can_view_transactions BOOLEAN DEFAULT 1,
                    can_edit_patients BOOLEAN DEFAULT 1,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP
                )
            '''))
            db.session.commit()
        except:
            pass
        
        db.create_all()
        
        # ===== Migration: add follow-up fields to appointments =====
        from sqlalchemy import inspect as sa_inspect
        inspector = sa_inspect(db.engine)
        appt_cols = [c['name'] for c in inspector.get_columns('appointments')]

        # ===== Migration: add treatment_plans table =====
        if 'treatment_plans' in inspector.get_table_names():
            treat_cols = [c['name'] for c in inspector.get_columns('treatment_plans')]
        else:
            treat_cols = []
        if not treat_cols:
            try:
                db.session.execute(sa_text('''
                    CREATE TABLE IF NOT EXISTS treatment_plans (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
                        section VARCHAR(20) NOT NULL DEFAULT '检查',
                        batch VARCHAR(20),
                        tooth_mark VARCHAR(200),
                        note TEXT,
                        sort_order INTEGER DEFAULT 0,
                        created_at TIMESTAMP,
                        updated_at TIMESTAMP
                    )
                '''))
                db.session.commit()
                print('📌 Created treatment_plans table')
            except Exception:
                db.session.rollback()
        
        # Migrate: add batch column to existing treatment_plans
        if 'treatment_plans' in inspector.get_table_names():
            treat_cols = [c['name'] for c in inspector.get_columns('treatment_plans')]
            if 'batch' not in treat_cols:
                try:
                    db.session.execute(sa_text('ALTER TABLE treatment_plans ADD COLUMN batch VARCHAR(20)'))
                    db.session.commit()
                    print('📌 Added batch column to treatment_plans')
                except Exception:
                    db.session.rollback()

        # ===== Migration: add cost_items table =====
        if 'cost_items' not in inspector.get_table_names():
            try:
                db.session.execute(sa_text('''
                    CREATE TABLE IF NOT EXISTS cost_items (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        treatment_plan_id INTEGER NOT NULL REFERENCES treatment_plans(id) ON DELETE CASCADE,
                        major_category VARCHAR(100) DEFAULT '',
                        sub_category VARCHAR(100) DEFAULT '',
                        unit_price FLOAT DEFAULT 0,
                        quantity INTEGER DEFAULT 1,
                        discount_rate FLOAT DEFAULT 0,
                        total_price FLOAT DEFAULT 0,
                        sort_order INTEGER DEFAULT 0,
                        created_at TIMESTAMP
                    )
                '''))
                db.session.commit()
                print('📌 Created cost_items table')
            except Exception:
                db.session.rollback()
        
        followup_fields = {
            'doctor': 'VARCHAR(100)',
            'treatment_project': 'VARCHAR(200)',
            'total_fee': 'FLOAT DEFAULT 0',
            'paid_fee': 'FLOAT DEFAULT 0',
        }
        for fname, ftype in followup_fields.items():
            if fname not in appt_cols:
                try:
                    db.session.execute(sa_text(f'ALTER TABLE appointments ADD COLUMN {fname} {ftype}'))
                    db.session.commit()
                    print(f'📌 Added appointments.{fname}')
                except Exception:
                    db.session.rollback()

        # ===== Migration: add internal_id column if missing in existing DB =====
        cols = [c['name'] for c in inspector.get_columns('patients')]
        if 'internal_id' not in cols:
            try:
                db.session.execute(sa_text('ALTER TABLE patients ADD COLUMN internal_id VARCHAR(20)'))
                db.session.commit()
                print('📌 Added internal_id column')
            except Exception:
                db.session.rollback()

        # Generate internal_id for existing patients
        missing = Patient.query.filter(Patient.internal_id.is_(None)).all()
        for p in missing:
            p.internal_id = f'MEYA-{p.id:04d}'
        if missing:
            db.session.commit()
            print(f'📌 Generated internal_id for {len(missing)} patients')

        # Handle duplicate phone numbers (remove unique constraint is complex,
        # instead just dedupe on the fly)
        dupe_phones = db.session.query(
            Patient.phone, db.func.count(Patient.id)
        ).filter(
            Patient.phone != '', Patient.phone.isnot(None)
        ).group_by(Patient.phone).having(db.func.count(Patient.id) > 1).all()
        for phone, cnt in dupe_phones:
            patients = Patient.query.filter_by(phone=phone).order_by(Patient.id).all()
            keep = patients[0]
            for dup in patients[1:]:
                # Merge appointments and transactions to the kept patient
                Appointment.query.filter_by(patient_id=dup.id).update({'patient_id': keep.id})
                Transaction.query.filter_by(patient_id=dup.id).update({'patient_id': keep.id})
                db.session.delete(dup)
            print(f'📌 Merged {cnt-1} duplicate(s) for phone {phone}')
        if dupe_phones:
            db.session.commit()
        
        # ===== Migration: add new permission columns to employees =====
        if 'employees' in inspector.get_table_names():
            emp_cols = [c['name'] for c in inspector.get_columns('employees')]
            # Add employee_type column
            if 'employee_type' not in emp_cols:
                try:
                    db.session.execute(sa_text("ALTER TABLE employees ADD COLUMN employee_type VARCHAR(30) DEFAULT 'clinic_staff'"))
                    print('📌 Migrated: added employees.employee_type')
                except Exception as e:
                    print(f'⚠️ Migration skip employees.employee_type: {e}')
            new_cols = [
                ('can_view_reports', 'BOOLEAN DEFAULT 1'),
                ('can_view_performance', 'BOOLEAN DEFAULT 1'),
                ('can_view_images', 'BOOLEAN DEFAULT 1'),
                ('can_view_treatment_plans', 'BOOLEAN DEFAULT 1'),
                ('can_view_consultations', 'BOOLEAN DEFAULT 1'),
            ]
            for col_name, col_def in new_cols:
                if col_name not in emp_cols:
                    try:
                        db.session.execute(sa_text(f'ALTER TABLE employees ADD COLUMN {col_name} {col_def}'))
                        print(f'📌 Migrated: added employees.{col_name}')
                    except Exception as e:
                        print(f'⚠️ Migration skip employees.{col_name}: {e}')
            db.session.commit()

        # ===== Migration: add indexes for performance =====
        index_sqls = [
            'CREATE INDEX IF NOT EXISTS idx_appt_scheduled_date ON appointments(scheduled_date)',
            'CREATE INDEX IF NOT EXISTS idx_appt_visit_type ON appointments(visit_type)',
            'CREATE INDEX IF NOT EXISTS idx_appt_inviter ON appointments(inviter)',
            'CREATE INDEX IF NOT EXISTS idx_appt_actual_visit ON appointments(actual_visit)',
            'CREATE INDEX IF NOT EXISTS idx_txn_payment_date ON transactions(payment_date)',
            'CREATE INDEX IF NOT EXISTS idx_txn_consultant ON transactions(consultant)',
            'CREATE INDEX IF NOT EXISTS idx_patient_online_consultant ON patients(online_consultant)',
            'CREATE INDEX IF NOT EXISTS idx_cons_consultant ON consultations(consultant)',
            'CREATE INDEX IF NOT EXISTS idx_cons_date ON consultations(date)',
        ]
        for sql in index_sqls:
            try:
                db.session.execute(sa_text(sql))
            except Exception as e:
                print(f'⚠️ Index skip: {e}')
        db.session.commit()
        print('📌 Indexes checked/created')

        # Import data if empty (rollback any pending failed ops first)
        try:
            db.session.rollback()
        except Exception:
            pass
        if Patient.query.count() == 0:
            print('📥 Auto-importing Excel data...')
            import import_data
            import_data.import_from_files(app)
            print(f'✅ Imported {Patient.query.count()} patients')
        
        _app_initialized = True
        _init_error = None
        return True
    except Exception as e:
        import traceback
        _init_error = str(e)
        print(f'⚠️ Init failed: {e}')
        traceback.print_exc()
        return False


@app.before_request
def check_initialized():
    """Ensure app is initialized before handling any request."""
    if request.path in ['/api/health', '/health']:
        return None
    if request.path.startswith('/static/'):
        return None
    if not _app_initialized:
        with app.app_context():
            ok = ensure_initialized()
        if not ok:
            return jsonify({
                'error': 'initializing',
                'message': f'服务启动中: {_init_error}'
            }), 503


@app.route('/api/health')
def api_health():
    ok = _app_initialized
    return jsonify({
        'status': 'ok' if ok else 'starting',
        'initialized': ok,
        'error': _init_error,
        'patients': Patient.query.count() if ok else -1,
        'tables': [] if ok else None,
    })


@app.route('/health')
def health_page():
    return api_health()


# =================== 咨询管理 ===================

@app.route('/consultations')
def consultations_page():
    return no_cache(render_template('base.html'))


@app.route('/api/consultations')
def api_consultations():
    perms = flask_session.get('permissions', {})
    if not perms.get('is_admin') and not perms.get('can_view_consultations'):
        return jsonify({'error': 'forbidden', 'message': '权限不足'}), 403
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '').strip()
    month = request.args.get('month', '').strip()
    has_appointment = request.args.get('has_appointment', '').strip()

    query = Consultation.query
    # Staff data isolation: only see own consultations
    staff = _staff_name()
    if staff:
        query = query.filter(Consultation.consultant == staff)
    if search:
        query = query.filter(
            or_(
                Consultation.patient_name.contains(search),
                Consultation.patient_phone.contains(search),
                Consultation.ad_code.contains(search),
                Consultation.consultant.contains(search),
            )
        )
    if month:
        try:
            y, m = month.split('-')
            query = query.filter(
                extract('year', Consultation.date) == int(y),
                extract('month', Consultation.date) == int(m)
            )
        except:
            pass
    if has_appointment:
        query = query.filter(Consultation.has_appointment == has_appointment)

    total = query.count()
    consultations = query.order_by(Consultation.date.desc(), Consultation.id.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page,
        'data': [c.to_dict() for c in consultations.items]
    })


@app.route('/api/consultations/<int:cid>')
def api_get_consultation(cid):
    c = Consultation.query.get_or_404(cid)
    return jsonify({'success': True, 'data': c.to_dict()})


@app.route('/api/consultations', methods=['POST'])
def api_create_consultation():
    perms = flask_session.get('permissions', {})
    if not perms.get('is_admin') and not perms.get('can_view_consultations'):
        return jsonify({'error': 'forbidden', 'message': '权限不足'}), 403
    data = request.get_json()
    
    c = Consultation(
        date=_parse_date(data.get('date')),
        patient_name=data.get('patient_name', '').strip(),
        patient_phone=normalize_phone(data.get('patient_phone', '')),
        ad_code=data.get('ad_code', '').strip(),
        has_reply=data.get('has_reply', '否'),
        has_appointment=data.get('has_appointment', '否'),
        appointment_success_time=datetime.now() if data.get('has_appointment') == '是' else None,
        appointment_date=_parse_date(data.get('appointment_date')) if data.get('has_appointment') == '是' else None,
        appointment_time=data.get('appointment_time', '').strip() if data.get('has_appointment') == '是' else '',
        consultant=data.get('consultant', '').strip(),
    )
    db.session.add(c)
    db.session.flush()  # Get c.id
    
    # 如果预约=是，自动推送到初诊预约
    if c.has_appointment == '是':
        phone = normalize_phone(c.patient_phone) if c.patient_phone else None
        name = c.patient_name.strip() if c.patient_name else ''
        
        # 查找或创建患者
        patient = None
        if phone:
            patient = Patient.query.filter_by(phone=phone).first()
        if not patient and name:
            patient = Patient.query.filter_by(name=name).first()
        
        if not patient:
            last = Patient.query.order_by(Patient.id.desc()).first()
            next_num = (last.id + 1) if last else 1
            patient = Patient(
                internal_id=f'MEYA-{next_num:04d}',
                name=name,
                phone=phone,
            )
            db.session.add(patient)
            db.session.flush()
        else:
            # 更新已有患者信息
            if name and not patient.name:
                patient.name = name
            if phone and not patient.phone:
                patient.phone = phone
            patient.updated_at = datetime.now()
        
        # 创建初诊预约
        appt = Appointment(
            patient_id=patient.id,
            scheduled_date=c.appointment_date or c.date,
            scheduled_time=c.appointment_time or '',
            inviter=c.consultant or '',
            phone=phone,
            visit_type='初诊',
            consultation_notes=f'咨询ID#{c.id} - 广告编码{c.ad_code or ""} 自动创建',
        )
        db.session.add(appt)
        db.session.flush()
        
        c.appointment_id = appt.id
    
    db.session.commit()
    
    result = c.to_dict()
    sse_broadcast('consultation_created', result)
    if c.has_appointment == '是':
        # 也广播预约创建事件
        appt_data = Appointment.query.get(c.appointment_id)
        if appt_data:
            sse_broadcast('appointment_created', appt_data.to_dict())
    
    return jsonify({'success': True, 'data': result})


@app.route('/api/consultations/<int:cid>', methods=['PUT'])
def api_update_consultation(cid):
    c = Consultation.query.get_or_404(cid)
    data = request.get_json()
    
    old_has_appointment = c.has_appointment
    
    for field in ['patient_name', 'patient_phone', 'ad_code', 'has_reply', 'has_appointment',
                   'appointment_time', 'consultant']:
        if field in data:
            val = data[field]
            if field == 'patient_phone' and val:
                val = normalize_phone(val)
            setattr(c, field, val.strip() if isinstance(val, str) else val)
    
    if 'date' in data:
        c.date = _parse_date(data['date'])
    if 'appointment_date' in data:
        c.appointment_date = _parse_date(data['appointment_date'])
    if 'appointment_success_time' in data and data['appointment_success_time']:
        c.appointment_success_time = _parse_date(data['appointment_success_time'])
    
    # 如果从"否"变为"是"，自动推送到初诊预约
    if c.has_appointment == '是' and old_has_appointment != '是':
        if not c.appointment_success_time:
            c.appointment_success_time = datetime.now()
        
        phone = normalize_phone(c.patient_phone) if c.patient_phone else None
        name = c.patient_name.strip() if c.patient_name else ''
        
        patient = None
        if phone:
            patient = Patient.query.filter_by(phone=phone).first()
        if not patient and name:
            patient = Patient.query.filter_by(name=name).first()
        
        if not patient:
            last = Patient.query.order_by(Patient.id.desc()).first()
            next_num = (last.id + 1) if last else 1
            patient = Patient(
                internal_id=f'MEYA-{next_num:04d}',
                name=name,
                phone=phone,
            )
            db.session.add(patient)
            db.session.flush()
        else:
            if name and not patient.name:
                patient.name = name
            if phone and not patient.phone:
                patient.phone = phone
            patient.updated_at = datetime.now()
        
        appt = Appointment(
            patient_id=patient.id,
            scheduled_date=c.appointment_date or c.date,
            scheduled_time=c.appointment_time or '',
            inviter=c.consultant or '',
            phone=phone,
            visit_type='初诊',
            consultation_notes=f'咨询ID#{c.id} - 广告编码{c.ad_code or ""} 自动创建',
        )
        db.session.add(appt)
        db.session.flush()
        
        c.appointment_id = appt.id
    
    # 如果从"是"变为"否"，删除关联的预约（可选：仅当该预约没有其他操作时）
    elif c.has_appointment != '是' and old_has_appointment == '是' and c.appointment_id:
        # 不自动删除，让用户手动在预约管理中处理
        pass
    
    db.session.commit()
    
    result = c.to_dict()
    sse_broadcast('consultation_updated', result)
    if c.has_appointment == '是' and old_has_appointment != '是' and c.appointment_id:
        appt_data = Appointment.query.get(c.appointment_id)
        if appt_data:
            sse_broadcast('appointment_created', appt_data.to_dict())
    
    return jsonify({'success': True, 'data': result})


@app.route('/api/consultations/<int:cid>', methods=['DELETE'])
def api_delete_consultation(cid):
    c = Consultation.query.get_or_404(cid)
    db.session.delete(c)
    db.session.commit()
    sse_broadcast('consultation_deleted', {'id': cid})
    return jsonify({'success': True})


@app.route('/api/fix/phones')
def api_fix_phones():
    """One-time: add 60 prefix to all patient phone numbers."""
    if flask_session.get('user_role') != 'admin':
        return jsonify({'error': 'forbidden'}), 403
    updated = 0
    for p in Patient.query.filter(Patient.phone != '', Patient.phone.isnot(None)).all():
        phone = p.phone.strip()
        if phone and not phone.startswith('60'):
            p.phone = '60' + phone
            updated += 1
    db.session.commit()
    return jsonify({'success': True, 'updated': updated})


def _parse_float(s):
    if not s or s == '' or s == 'None':
        return 0.0
    s = str(s).replace('RM', '').replace('RM', '').replace(',', '').replace(' ', '')
    try:
        return float(s)
    except:
        return 0.0


def _parse_int(s):
    if not s or s == '' or s == 'None':
        return 0
    try:
        return int(float(str(s).strip()))
    except:
        return 0


# Initialization happens on first request (see check_initialized above)

if __name__ == '__main__':

    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    host = '0.0.0.0' if os.environ.get('RENDER') else '127.0.0.1'
    app.run(host=host, port=port, debug=debug)
