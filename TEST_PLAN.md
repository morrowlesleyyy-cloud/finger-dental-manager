# MEYA Dental 牙科管理系统 - 测试计划

**版本:** 1.0  
**日期:** 2026-06-28  
**测试工程师:** Finger 🖐️  
**服务地址:** http://127.0.0.1:5000  

---

## 1. 测试环境

| 项目 | 说明 |
|------|------|
| 框架 | Flask + SQLite |
| 架构 | SPA (base.html) |
| 认证 | Session-based, Cookie |
| 测试工具 | curl + cookie jar |
| 测试范围 | 全部13个模块 |

## 2. 测试角色

| 角色 | 账号 | 密码 | 分类 | 数据隔离 |
|------|------|------|------|----------|
| admin | admin | admin123 | - | 全部数据 |
| 网咨人员 | test_online | test123 | online_consultant | 只看自己数据 |
| 门诊人员 | test_clinic | test123 | clinic_staff | 全部数据 |

## 3. 测试用例

### 3.1 登录认证 (Auth)

| TC-ID | 用例名称 | 测试步骤 | 预期结果 |
|-------|----------|----------|----------|
| AUTH-01 | admin 登录成功 | POST /api/login {"username":"admin","password":"admin123"} | 200, success=true, role=admin |
| AUTH-02 | 错误密码登录 | POST /api/login {"username":"admin","password":"wrong"} | 401, success=false |
| AUTH-03 | 不存在的用户 | POST /api/login {"username":"nonexist","password":"123"} | 401 |
| AUTH-04 | 空用户名 | POST /api/login {"username":"","password":"123"} | 401 |
| AUTH-05 | 空密码 | POST /api/login {"username":"admin","password":""} | 401 |
| AUTH-06 | 退出登录 | POST /api/logout | 200, success=true |
| AUTH-07 | 未登录访问 API | GET /api/patients (不带 cookie) | 401, error=unauthorized |
| AUTH-08 | 未登录访问页面 | GET /appointments (不带 cookie) | 302 重定向到 /login |
| AUTH-09 | 登出后访问 API | POST /api/logout → GET /api/patients | 401 |
| AUTH-10 | Auth Check API | GET /api/auth/check | 200, 返回当前用户信息 |
| AUTH-11 | 员工账号登录 | POST /api/login {"username":"test_online","password":"test123"} | 200, success=true, role=staff |

### 3.2 首页看板 (Dashboard)

| TC-ID | 用例名称 | 测试步骤 | 预期结果 |
|-------|----------|----------|----------|
| DASH-01 | admin 查看看板 | GET /api/dashboard (admin cookie) | 200, 包含所有看板统计字段 |
| DASH-02 | 网咨人员看板数据隔离 | GET /api/dashboard (网咨 cookie) | 200, 只显示该网咨的数据 |
| DASH-03 | 门诊人员看板 | GET /api/dashboard (门诊 cookie) | 200, 显示全部数据 |
| DASH-04 | 看板响应结构验证 | 检查返回 JSON 字段 | 包含 today_appointments, monthly_revenue 等字段 |

### 3.3 患者管理 (Patients)

| TC-ID | 用例名称 | 测试步骤 | 预期结果 |
|-------|----------|----------|----------|
| PAT-01 | 获取患者列表 | GET /api/patients?page=1&per_page=10 | 200, 返回分页数据 |
| PAT-02 | 搜索患者 | GET /api/patients?search=测试 | 200, 返回匹配数据 |
| PAT-03 | 创建患者 | POST /api/patients {"name":"测试患者","phone":"0129998881"} | 200, success=true, 自动生成 MEYA-XXXX |
| PAT-04 | 创建重复电话患者（合并） | POST /api/patients (同上电话) | 200, merged=true |
| PAT-05 | 更新患者 | PUT /api/patients/{id} {"gender":"男"} | 200, 数据已更新 |
| PAT-06 | 删除患者 | DELETE /api/patients/{id} | 200, success=true |
| PAT-07 | 获取患者详情 | GET /api/patients/{id} | 200, 含预约/成交/图片/治疗方案 |
| PAT-08 | 获取不存在的患者 | GET /api/patients/99999 | 404 |
| PAT-09 | 按日期筛选患者 | GET /api/patients?date=2026-06-01 | 200 |
| PAT-10 | 网咨人员只能看自己的患者 | GET /api/patients (网咨 cookie) | 只返回 online_consultant 匹配的数据 |
| PAT-11 | 创建患者空姓名 | POST /api/patients {"name":"","phone":"0123456789"} | 允许创建（name 可为空字符串） |

### 3.4 初诊预约 (Appointments - 初诊)

| TC-ID | 用例名称 | 测试步骤 | 预期结果 |
|-------|----------|----------|----------|
| APT-01 | 获取初诊预约列表 | GET /api/appointments?visit_type=初诊 | 200, 返回初诊预约列表 |
| APT-02 | 按状态筛选 | GET /api/appointments?visit_type=初诊&status=today | 200 |
| APT-03 | 按月筛选 | GET /api/appointments?visit_type=初诊&month=2026-06 | 200 |
| APT-04 | 创建初诊预约（关联患者） | POST /api/appointments {"patient_id":{id},"scheduled_date":"2026-07-01","visit_type":"初诊"} | 200, success=true |
| APT-05 | 创建初诊预约（按姓名自动创建患者） | POST /api/appointments {"patient_name":"新患者","phone":"0120001111","scheduled_date":"2026-07-01","visit_type":"初诊"} | 200, 自动创建患者 |
| APT-06 | 更新预约 | PUT /api/appointments/{id} {"actual_visit":"成交"} | 200, 已更新 |
| APT-07 | 删除预约 | DELETE /api/appointments/{id} | 200, success=true |
| APT-08 | 创建预约无患者信息 | POST /api/appointments {"scheduled_date":"2026-07-01"} | 400, 提示提供患者信息 |
| APT-09 | 搜索预约 | GET /api/appointments?visit_type=初诊&search=测试 | 200 |
| APT-10 | 网咨人员只看自己预约 | GET /api/appointments?visit_type=初诊 (网咨 cookie) | 只返回 inviter 匹配的预约 |

### 3.5 复诊预约 (Appointments - 复诊)

| TC-ID | 用例名称 | 测试步骤 | 预期结果 |
|-------|----------|----------|----------|
| FUP-01 | 获取复诊预约列表 | GET /api/appointments?visit_type=复诊 | 200 |
| FUP-02 | 创建复诊预约 | POST /api/appointments {"patient_id":{id},"scheduled_date":"2026-07-10","visit_type":"复诊","doctor":"张医生","treatment_project":"补牙"} | 200 |
| FUP-03 | 更新复诊费用 | PUT /api/appointments/{id} {"total_fee":5000,"paid_fee":2000} | 200, balance=3000 |

### 3.6 成交管理 (Transactions)

| TC-ID | 用例名称 | 测试步骤 | 预期结果 |
|-------|----------|----------|----------|
| TXN-01 | 获取成交列表 | GET /api/transactions?page=1 | 200, 返回分页数据 |
| TXN-02 | 按月筛选 | GET /api/transactions?month=2026-06 | 200 |
| TXN-03 | 搜索成交 | GET /api/transactions?search=种植 | 200 |
| TXN-04 | 创建成交 | POST /api/transactions {"patient_id":{id},"plan_type":"种植","brand":"瑞士ITI","performance_amount":30000,"visit_outcome":"成交"} | 200, success=true |
| TXN-05 | 创建成交（自动创建患者） | POST /api/transactions {"patient_name":"自动创建","phone":"0119990001","plan_type":"全科","performance_amount":5000} | 200, 自动创建患者 |
| TXN-06 | 更新成交 | PUT /api/transactions/{id} {"performance_amount":35000} | 200 |
| TXN-07 | 删除成交 | DELETE /api/transactions/{id} | 200, success=true |
| TXN-08 | 创建成交无患者信息 | POST /api/transactions {} | 400 |
| TXN-09 | 网咨人员只看自己成交 | GET /api/transactions (网咨 cookie) | 只返回 consultant 匹配的成交 |

### 3.7 数据报表 (Reports)

| TC-ID | 用例名称 | 测试步骤 | 预期结果 |
|-------|----------|----------|----------|
| REP-01 | 月度明细报表 | GET /api/reports/monthly?year=2026&month=6 | 200, 含每日预约/成交/收款 |
| REP-02 | 年度总览 | GET /api/reports/overview?year=2026 | 200, 含月度业绩/咨询师排名/来源分析 |
| REP-03 | 月度报表缺少参数 | GET /api/reports/monthly | 使用默认值 |
| REP-04 | 网咨人员报表数据隔离 | GET /api/reports/monthly (网咨 cookie) | 只显示自己数据 |
| REP-05 | 门诊人员可看报表 | GET /api/reports/monthly (门诊 cookie) | 200, 全部数据 |

### 3.8 业绩管理 (Performance)

| TC-ID | 用例名称 | 测试步骤 | 预期结果 |
|-------|----------|----------|----------|
| PERF-01 | 查看当月业绩 | GET /api/performance?year=2026&month=6 | 200, 含网咨业绩+咨询师业绩 |
| PERF-02 | 业绩使用默认月份 | GET /api/performance | 200 |
| PERF-03 | 网咨人员业绩隔离 | GET /api/performance (网咨 cookie) | 只看自己的 |
| PERF-04 | 门诊人员可看业绩 | GET /api/performance (门诊 cookie) | 200, 全部数据 |

### 3.9 患者图片 (Patient Images)

| TC-ID | 用例名称 | 测试步骤 | 预期结果 |
|-------|----------|----------|----------|
| IMG-01 | 获取患者图片列表 | GET /api/patients/{id}/images | 200, 返回图片数组 |
| IMG-02 | 图片汇总页面 | GET /api/patients/images-summary | 200, 含术前术后数量 |
| IMG-03 | 删除图片 | DELETE /api/images/{id} | 200, success=true |
| IMG-04 | 获取不存在的图片 | GET /api/images/nonexistent.jpg | 404 |
| IMG-05 | 网咨人员可查看图片 | GET /api/patients/{id}/images (网咨 cookie) | 200 |

### 3.10 治疗方案 (Treatment Plans)

| TC-ID | 用例名称 | 测试步骤 | 预期结果 |
|-------|----------|----------|----------|
| PLAN-01 | 获取治疗方案列表 | GET /api/patients/{id}/treatment-plans | 200, 返回方案数组 |
| PLAN-02 | 创建检查方案 | POST /api/patients/{id}/treatment-plans {"section":"检查","tooth_mark":"{\"11\":\"O\"}","note":"龋齿"} | 200 |
| PLAN-03 | 创建治疗方案 | POST /api/patients/{id}/treatment-plans {"section":"治疗方案","batch":"批次一"} | 200 |
| PLAN-04 | 更新方案 | PUT /api/treatment-plans/{id} {"note":"修改备注"} | 200 |
| PLAN-05 | 删除方案 | DELETE /api/treatment-plans/{id} | 200 |
| PLAN-06 | 添加费用明细 | POST /api/treatment-plans/{id}/cost-items {"major_category":"种植体","unit_price":12000,"quantity":2} | 200 |
| PLAN-07 | 更新费用项 | PUT /api/cost-items/{id} {"discount_rate":10} | 200 |
| PLAN-08 | 删除费用项 | DELETE /api/cost-items/{id} | 200 |

### 3.11 咨询管理 (Consultations)

| TC-ID | 用例名称 | 测试步骤 | 预期结果 |
|-------|----------|----------|----------|
| CONS-01 | 获取咨询列表 | GET /api/consultations | 200 |
| CONS-02 | 创建咨询（预约=否） | POST /api/consultations {"date":"2026-06-28","patient_name":"咨询患者","patient_phone":"0112223334","ad_code":"FB-001","has_appointment":"否"} | 200, 不创建预约 |
| CONS-03 | 创建咨询（预约=是） | POST /api/consultations {"date":"2026-06-28","patient_name":"预约患者","patient_phone":"0112223335","ad_code":"FB-002","has_appointment":"是","appointment_date":"2026-07-01","consultant":"测试咨询师"} | 200, 自动创建患者+初诊预约 |
| CONS-04 | 更新咨询（否→是） | PUT /api/consultations/{id} {"has_appointment":"是"} | 200, 自动推送到预约 |
| CONS-05 | 删除咨询 | DELETE /api/consultations/{id} | 200 |
| CONS-06 | 网咨人员咨询隔离 | GET /api/consultations (网咨 cookie) | 只看自己的 |

### 3.12 员工管理 (Employees)

| TC-ID | 用例名称 | 测试步骤 | 预期结果 |
|-------|----------|----------|----------|
| EMP-01 | admin 查看员工列表 | GET /api/employees (admin cookie) | 200, 返回员工列表 |
| EMP-02 | 创建员工 | POST /api/employees {"username":"test_staff","password":"pass123","display_name":"测试员工"} | 200 |
| EMP-03 | 创建重复用户名 | POST /api/employees {"username":"test_staff","password":"pass123"} | 400, 用户名已存在 |
| EMP-04 | 创建员工空用户名 | POST /api/employees {"username":"","password":"pass123"} | 400 |
| EMP-05 | 更新员工 | PUT /api/employees/{id} {"display_name":"新名称"} | 200 |
| EMP-06 | 删除员工 | DELETE /api/employees/{id} | 200 |
| EMP-07 | 非 admin 创建员工 | POST /api/employees (网咨 cookie) | 403, forbidden |
| EMP-08 | 创建网咨类型员工 | POST /api/employees {"username":"test_online","password":"test123","employee_type":"online_consultant","display_name":"测试网咨"} | 200 |

### 3.13 数据隔离 (Data Isolation)

| TC-ID | 用例名称 | 测试步骤 | 预期结果 |
|-------|----------|----------|----------|
| ISO-01 | 网咨人员患者隔离 | admin创建患者online_consultant=admin → 网咨看不到 | 网咨查询患者列表不包含该患者 |
| ISO-02 | 网咨人员预约隔离 | 网咨可见自己的预约 | 其他inviter预约不可见 |
| ISO-03 | 网咨人员成交隔离 | 网咨可见自己的成交 | 其他consultant成交不可见 |
| ISO-04 | 门诊人员无隔离 | 门诊人员可看到所有数据 | 全量数据 |
| ISO-05 | admin无隔离 | admin 可看到所有数据 | 全量数据 |

### 3.14 权限控制 (Permission Control)

| TC-ID | 用例名称 | 测试步骤 | 预期结果 |
|-------|----------|----------|----------|
| PERM-01 | admin 全部权限 | admin 访问所有模块 | 全部 200 |
| PERM-02 | 员工无报表权限 | 创建权限关闭的员工 → GET /api/reports/monthly | 403 |
| PERM-03 | 员工无成交权限 | GET /api/transactions (无权限员工) | 403 |
| PERM-04 | 员工无业绩权限 | GET /api/performance (无权限员工) | 403 |
| PERM-05 | 员工无图片权限 | GET /api/patients/{id}/images (无权限员工) | 403 |
| PERM-06 | 员工无治疗方案权限 | GET /api/patients/{id}/treatment-plans (无权限员工) | 403 |
| PERM-07 | 员工无咨询权限 | GET /api/consultations (无权限员工) | 403 |

### 3.15 边界条件与异常 (Edge Cases)

| TC-ID | 用例名称 | 测试步骤 | 预期结果 |
|-------|----------|----------|----------|
| EDGE-01 | 超大页码 | GET /api/patients?page=99999 | 200, 返回空数组 |
| EDGE-02 | 非法日期格式 | POST /api/appointments {"scheduled_date":"not-a-date"} | 200, scheduled_date 为 null（容错） |
| EDGE-03 | 空JSON请求体 | POST /api/patients (空body) | 正常处理 |
| EDGE-04 | SQL注入尝试 | GET /api/patients?search=';DROP TABLE-- | 200, 无影响（ORM 防护） |
| EDGE-05 | XSS尝试 | POST /api/patients {"name":"<script>alert(1)</script>"} | 200, 存储原始值 |
| EDGE-06 | 长字符串 | POST /api/patients {"name":"(500字符)",...} | 正常处理或截断 |

## 4. 测试执行顺序

1. **环境准备** — 创建测试账号：网咨人员、门诊人员、权限受限员工
2. **认证测试** — 所有 AUTH 用例
3. **CRUD 测试** — 患者/预约/成交/咨询/治疗方案/图片 创建
4. **查询测试** — 各模块搜索/筛选/分页
5. **权限测试** — 角色隔离 + 模块权限
6. **边界测试** — 异常输入
7. **清理** — 删除测试数据

---

## 5. 通过标准

- ✅ Pass: 实际结果与预期一致
- ❌ Fail: 实际结果与预期不一致
- ⚠️ Warn: 行为偏离预期但影响较小
- ⏭️ Skip: 因环境限制跳过
