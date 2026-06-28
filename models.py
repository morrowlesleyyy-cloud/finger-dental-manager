"""Database models for MEYA Dental Management System."""
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date

db = SQLAlchemy()


class Patient(db.Model):
    """患者档案 - 核心主表"""
    __tablename__ = 'patients'

    id = db.Column(db.Integer, primary_key=True)
    internal_id = db.Column(db.String(20), unique=True, index=True)  # 内部编号: MEYA-0001
    name = db.Column(db.String(100), nullable=False, index=True)
    phone = db.Column(db.String(50), unique=True, index=True)  # 电话号码作为唯一标识
    gender = db.Column(db.String(10))
    age = db.Column(db.Integer)
    tooth_count = db.Column(db.String(50))  # 缺牙颗数: 少颗/多颗/半口/全口
    condition_desc = db.Column(db.Text)      # 患者情况描述
    source = db.Column(db.String(50))        # 客户来源: 网咨/转介绍/自然到店
    source_channel = db.Column(db.String(50)) # 线索来源渠道: FB/转介绍等
    online_consultant = db.Column(db.String(50))  # 网咨
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # Relations
    appointments = db.relationship('Appointment', backref='patient', lazy='dynamic',
                                   cascade='all, delete-orphan')
    transactions = db.relationship('Transaction', backref='patient', lazy='dynamic',
                                   cascade='all, delete-orphan')

    def to_dict(self):
        phone = self.phone or ''
        if phone and not phone.startswith('60'):
            phone = '60' + phone
        return {
            'id': self.id,
            'internal_id': self.internal_id or '',
            'name': self.name,
            'phone': phone,
            'gender': self.gender,
            'age': self.age,
            'tooth_count': self.tooth_count,
            'condition_desc': self.condition_desc,
            'source': self.source,
            'source_channel': self.source_channel,
            'online_consultant': self.online_consultant,
            'created_at': self.created_at.strftime('%Y-%m-%d') if self.created_at else '',
            'updated_at': self.updated_at.strftime('%Y-%m-%d') if self.updated_at else '',
        }


class Appointment(db.Model):
    """预约/跟进记录"""
    __tablename__ = 'appointments'

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)

    # 预约信息
    scheduled_date = db.Column(db.Date, index=True)
    scheduled_time = db.Column(db.String(50))
    inviter = db.Column(db.String(50))       # 邀约人
    inviter_2 = db.Column(db.String(50))     # 邀约人2
    phone = db.Column(db.String(50))

    # 到访信息
    visit_type = db.Column(db.String(50))    # 初诊/复诊/其他
    actual_visit = db.Column(db.String(50))  # 实际到访情况: 成交/未成交/定金/未到访等

    # 跟进
    consultation_notes = db.Column(db.Text)  # 咨询及跟进情况
    followup_24h = db.Column(db.Text)
    followup_7d = db.Column(db.Text)
    followup_15d = db.Column(db.Text)
    followup_30d = db.Column(db.Text)
    need_collab = db.Column(db.String(50))   # 是否需要协同跟进
    invalid_reason = db.Column(db.String(200))  # 无效原因
    has_continue = db.Column(db.String(50))  # 是否有续种

    registered_date = db.Column(db.Date)     # 登记日期

    # 复诊字段
    doctor = db.Column(db.String(100))           # 医生
    treatment_project = db.Column(db.String(200)) # 治疗项目
    total_fee = db.Column(db.Float, default=0)    # 总费用
    paid_fee = db.Column(db.Float, default=0)     # 已交费用

    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        pat = self.patient
        pat_name = pat.name if pat else ''
        pat_phone = (pat.phone or '') if pat else ''
        pat_internal = (pat.internal_id or '') if pat else ''
        return {
            'id': self.id,
            'patient_id': self.patient_id,
            'patient_name': pat_name,
            'patient_phone': pat_phone,
            'patient_internal_id': pat_internal,
            'scheduled_date': self.scheduled_date.strftime('%Y-%m-%d') if self.scheduled_date else '',
            'scheduled_time': self.scheduled_time or '',
            'inviter': self.inviter or '',
            'inviter_2': self.inviter_2 or '',
            'phone': self.phone or '',
            'visit_type': self.visit_type or '',
            'actual_visit': self.actual_visit or '',
            'consultation_notes': self.consultation_notes or '',
            'followup_24h': self.followup_24h or '',
            'followup_7d': self.followup_7d or '',
            'followup_15d': self.followup_15d or '',
            'followup_30d': self.followup_30d or '',
            'need_collab': self.need_collab or '',
            'invalid_reason': self.invalid_reason or '',
            'has_continue': self.has_continue or '',
            'registered_date': self.registered_date.strftime('%Y-%m-%d') if self.registered_date else '',
            'doctor': self.doctor or '',
            'treatment_project': self.treatment_project or '',
            'total_fee': self.total_fee or 0,
            'paid_fee': self.paid_fee or 0,
            'balance': (self.total_fee or 0) - (self.paid_fee or 0),
            'created_at': self.created_at.strftime('%Y-%m-%d') if self.created_at else '',
        }


class Employee(db.Model):
    """员工账号"""
    __tablename__ = 'employees'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    password = db.Column(db.String(200), nullable=False)
    display_name = db.Column(db.String(50), default='')
    role = db.Column(db.String(20), default='staff')  # admin / staff
    employee_type = db.Column(db.String(30), default='clinic_staff')  # online_consultant / clinic_staff

    # Permissions
    can_view_appointments = db.Column(db.Boolean, default=True)
    can_view_transactions = db.Column(db.Boolean, default=True)
    can_edit_patients = db.Column(db.Boolean, default=True)
    can_view_reports = db.Column(db.Boolean, default=True)
    can_view_performance = db.Column(db.Boolean, default=True)
    can_view_images = db.Column(db.Boolean, default=True)
    can_view_treatment_plans = db.Column(db.Boolean, default=True)
    can_view_consultations = db.Column(db.Boolean, default=True)

    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'display_name': self.display_name or '',
            'role': self.role,
            'employee_type': self.employee_type or 'clinic_staff',
            'can_view_appointments': bool(self.can_view_appointments),
            'can_view_transactions': bool(self.can_view_transactions),
            'can_edit_patients': bool(self.can_edit_patients),
            'can_view_reports': bool(self.can_view_reports),
            'can_view_performance': bool(self.can_view_performance),
            'can_view_images': bool(self.can_view_images),
            'can_view_treatment_plans': bool(self.can_view_treatment_plans),
            'can_view_consultations': bool(self.can_view_consultations),
            'is_active': bool(self.is_active),
            'created_at': self.created_at.strftime('%Y-%m-%d') if self.created_at else '',
        }


class Transaction(db.Model):
    """成交/财务记录"""
    __tablename__ = 'transactions'

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)

    # 方案信息
    plan_type = db.Column(db.String(50))       # 方案类型: 种植/全科
    plan_detail = db.Column(db.String(200))    # 方案详情
    brand = db.Column(db.String(50))           # 品牌
    tooth_positions = db.Column(db.String(200))  # 牙位
    tooth_count = db.Column(db.Integer)        # 颗数
    bone_graft = db.Column(db.String(50))      # 骨粉
    bone_membrane = db.Column(db.String(50))   # 骨膜
    sinus_lift = db.Column(db.String(50))      # 内外提

    # 财务信息
    deposit_amount = db.Column(db.Float, default=0)       # 定金金额
    deposit_contract = db.Column(db.Float, default=0)     # 定金合同金额
    deposit_date = db.Column(db.Date)                     # 定金日期
    deposit_return_date = db.Column(db.Date)              # 定金回款日期

    performance_amount = db.Column(db.Float, default=0)   # 业绩金额(半款)
    paid_amount = db.Column(db.Float, default=0)          # 已付金额(半款)
    payment_date = db.Column(db.Date)                     # 交款日期

    total_amount = db.Column(db.Float, default=0)         # 成交额
    payment = db.Column(db.Float, default=0)              # 支付额
    payment_date_2 = db.Column(db.Date)                   # 成交日期
    supplement_amount = db.Column(db.Float, default=0)    # 补费额
    supplement_date = db.Column(db.Date)                  # 补费日期
    debt_amount = db.Column(db.Float, default=0)          # 欠款额
    supplement_records = db.Column(db.Text)               # 补费记录

    # 治疗信息
    treatment_date = db.Column(db.Date)
    treatment_doctor = db.Column(db.String(50))

    # 成交分类
    visit_outcome = db.Column(db.String(50))   # 成交类型: 成交/定金/定金转成交/未成交转成交等
    consultant = db.Column(db.String(50))      # 谈单人/咨询师

    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        pat = self.patient
        pat_name = pat.name if pat else ''
        pat_phone = (pat.phone or '') if pat else ''
        pat_internal = (pat.internal_id or '') if pat else ''
        return {
            'id': self.id,
            'patient_id': self.patient_id,
            'patient_name': pat_name,
            'patient_phone': pat_phone,
            'patient_internal_id': pat_internal,
            'plan_type': self.plan_type or '',
            'plan_detail': self.plan_detail or '',
            'brand': self.brand or '',
            'tooth_positions': self.tooth_positions or '',
            'tooth_count': self.tooth_count,
            'bone_graft': self.bone_graft or '',
            'bone_membrane': self.bone_membrane or '',
            'sinus_lift': self.sinus_lift or '',
            'deposit_amount': self.deposit_amount or 0,
            'deposit_contract': self.deposit_contract or 0,
            'deposit_date': self.deposit_date.strftime('%Y-%m-%d') if self.deposit_date else '',
            'deposit_return_date': self.deposit_return_date.strftime('%Y-%m-%d') if self.deposit_return_date else '',
            'performance_amount': self.performance_amount or 0,
            'paid_amount': self.paid_amount or 0,
            'payment_date': self.payment_date.strftime('%Y-%m-%d') if self.payment_date else '',
            'total_amount': self.total_amount or 0,
            'payment': self.payment or 0,
            'payment_date_2': self.payment_date_2.strftime('%Y-%m-%d') if self.payment_date_2 else '',
            'supplement_amount': self.supplement_amount or 0,
            'supplement_date': self.supplement_date.strftime('%Y-%m-%d') if self.supplement_date else '',
            'debt_amount': self.debt_amount or 0,
            'supplement_records': self.supplement_records or '',
            'treatment_date': self.treatment_date.strftime('%Y-%m-%d') if self.treatment_date else '',
            'treatment_doctor': self.treatment_doctor or '',
            'visit_outcome': self.visit_outcome or '',
            'consultant': self.consultant or '',
            'created_at': self.created_at.strftime('%Y-%m-%d') if self.created_at else '',
        }


class TreatmentPlan(db.Model):
    """治疗方案 - 检查 + 治疗计划"""
    __tablename__ = 'treatment_plans'

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    section = db.Column(db.String(20), nullable=False, default='检查')  # 检查 / 治疗方案
    batch = db.Column(db.String(20))          # 批次: 批次一 ~ 批次五
    tooth_mark = db.Column(db.String(200))   # 牙科十字标记 (JSON)
    note = db.Column(db.Text)               # 备注
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    patient = db.relationship('Patient', backref=db.backref('treatment_plans', lazy='dynamic', cascade='all, delete-orphan'))

    def to_dict(self):
        cost_items_list = [ci.to_dict() for ci in self.cost_items.order_by(CostItem.sort_order).all()]
        cost_total = sum(ci['total_price'] for ci in cost_items_list)
        return {
            'id': self.id,
            'patient_id': self.patient_id,
            'section': self.section,
            'batch': self.batch or '',
            'tooth_mark': self.tooth_mark or '',
            'note': self.note or '',
            'sort_order': self.sort_order,
            'cost_items': cost_items_list,
            'cost_total': cost_total,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else '',
        }


class CostItem(db.Model):
    """费用明细 - 关联治疗方案的具体费用项"""
    __tablename__ = 'cost_items'

    id = db.Column(db.Integer, primary_key=True)
    treatment_plan_id = db.Column(db.Integer, db.ForeignKey('treatment_plans.id', ondelete='CASCADE'), nullable=False)
    major_category = db.Column(db.String(100), default='')   # 大类: 种植体/牙冠/骨粉/骨膜/内外提/其他
    sub_category = db.Column(db.String(100), default='')      # 小类: 品牌型号/具体项目
    unit_price = db.Column(db.Float, default=0)               # 单价
    quantity = db.Column(db.Integer, default=1)               # 数量
    discount_rate = db.Column(db.Float, default=0)            # 折扣率 (%)
    total_price = db.Column(db.Float, default=0)              # 总价
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.now)

    treatment_plan = db.relationship('TreatmentPlan', backref=db.backref('cost_items', lazy='dynamic', cascade='all, delete-orphan'))

    def to_dict(self):
        return {
            'id': self.id,
            'treatment_plan_id': self.treatment_plan_id,
            'major_category': self.major_category or '',
            'sub_category': self.sub_category or '',
            'unit_price': self.unit_price or 0,
            'quantity': self.quantity or 1,
            'discount_rate': self.discount_rate or 0,
            'total_price': self.total_price or 0,
            'sort_order': self.sort_order,
        }


class PatientImage(db.Model):
    """患者图片 - 术前术后对比照"""
    __tablename__ = 'patient_images'

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    stage = db.Column(db.String(20), nullable=False)      # 术前 / 术后
    category = db.Column(db.String(20), nullable=False)    # 口内照 / 全景片
    sub_type = db.Column(db.String(50))                    # 上颌颌面 / 左侧咬合 / 正面咬合 / 右侧咬合 / 下颌颌面 / 特写照
    filename = db.Column(db.String(255), nullable=False)   # 服务器存储文件名
    original_name = db.Column(db.String(255))              # 原始文件名
    position = db.Column(db.Integer, default=0)            # 同位置多张排序
    created_at = db.Column(db.DateTime, default=datetime.now)

    patient = db.relationship('Patient', backref=db.backref('images', lazy='dynamic', cascade='all, delete-orphan'))

    def to_dict(self):
        return {
            'id': self.id,
            'patient_id': self.patient_id,
            'stage': self.stage,
            'category': self.category,
            'sub_type': self.sub_type or '',
            'filename': self.filename,
            'original_name': self.original_name or '',
            'position': self.position,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else '',
            'url': f'/api/images/{self.filename}',
        }


class Consultation(db.Model):
    """咨询管理 - 广告进来的客户咨询"""
    __tablename__ = 'consultations'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, index=True)                    # 咨询日期
    patient_name = db.Column(db.String(100))                 # 患者姓名
    patient_phone = db.Column(db.String(50))                 # 患者电话
    ad_code = db.Column(db.String(100))                      # 广告编码
    has_reply = db.Column(db.String(10), default='否')       # 是否有回复: 是/否
    has_appointment = db.Column(db.String(10), default='否') # 是否预约: 是/否
    appointment_success_time = db.Column(db.DateTime)        # 预约成功的时间
    appointment_date = db.Column(db.Date)                    # 预约日期
    appointment_time = db.Column(db.String(50))              # 预约时间
    consultant = db.Column(db.String(50))                    # 网咨人员
    appointment_id = db.Column(db.Integer)                   # 关联的预约ID
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date.strftime('%Y-%m-%d') if self.date else '',
            'patient_name': self.patient_name or '',
            'patient_phone': self.patient_phone or '',
            'ad_code': self.ad_code or '',
            'has_reply': self.has_reply or '否',
            'has_appointment': self.has_appointment or '否',
            'appointment_success_time': self.appointment_success_time.strftime('%Y-%m-%d %H:%M') if self.appointment_success_time else '',
            'appointment_date': self.appointment_date.strftime('%Y-%m-%d') if self.appointment_date else '',
            'appointment_time': self.appointment_time or '',
            'consultant': self.consultant or '',
            'appointment_id': self.appointment_id or 0,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else '',
        }
