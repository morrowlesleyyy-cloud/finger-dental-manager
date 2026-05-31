"""Database models for MEYA Dental Management System."""
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date

db = SQLAlchemy()


class Patient(db.Model):
    """患者档案 - 核心主表"""
    __tablename__ = 'patients'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    phone = db.Column(db.String(50), index=True)
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
        return {
            'id': self.id,
            'name': self.name,
            'phone': self.phone,
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
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'patient_id': self.patient_id,
            'patient_name': self.patient.name if self.patient else '',
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

    # Permissions
    can_view_appointments = db.Column(db.Boolean, default=True)
    can_view_transactions = db.Column(db.Boolean, default=True)
    can_edit_patients = db.Column(db.Boolean, default=True)

    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'display_name': self.display_name or '',
            'role': self.role,
            'can_view_appointments': bool(self.can_view_appointments),
            'can_view_transactions': bool(self.can_view_transactions),
            'can_edit_patients': bool(self.can_edit_patients),
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
        return {
            'id': self.id,
            'patient_id': self.patient_id,
            'patient_name': self.patient.name if self.patient else '',
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
