"""
种子数据生成器 v2 — 近6个月工单 & 人员数据
覆盖 2026-02-01 ~ 2026-07-26，生成真实业务场景模拟数据
"""
import random
import math
from datetime import datetime, date, timedelta, time

# ──────────────────────────────────────────────
# 0. 全局随机种子（保证可复现）
# ──────────────────────────────────────────────
random.seed(42)

# ──────────────────────────────────────────────
# 1. 角色数据
# ──────────────────────────────────────────────
ROLES = [
    "运维工程师",
    "高级运维",
    "数据库管理员",
    "网络管理员",
    "安全审计员",
    "系统架构师",
]

# ──────────────────────────────────────────────
# 2. 人员数据（20人，含中文姓名、手机号、入职日期）
# ──────────────────────────────────────────────
STAFF = [
    {"staff_no": "OP001", "name": "张伟",   "role_name": "高级运维",       "phone": "13812340001", "status": "启用", "hire_date": "2024-03-15"},
    {"staff_no": "OP002", "name": "李娜",   "role_name": "运维工程师",     "phone": "13912340002", "status": "启用", "hire_date": "2025-01-10"},
    {"staff_no": "OP003", "name": "王强",   "role_name": "数据库管理员",   "phone": "15012340003", "status": "启用", "hire_date": "2023-08-22"},
    {"staff_no": "OP004", "name": "赵敏",   "role_name": "网络管理员",     "phone": "18612340004", "status": "启用", "hire_date": "2024-06-01"},
    {"staff_no": "OP005", "name": "陈刚",   "role_name": "安全审计员",     "phone": "17712340005", "status": "启用", "hire_date": "2025-03-20"},
    {"staff_no": "OP006", "name": "周涛",   "role_name": "运维工程师",     "phone": "13512340006", "status": "停用", "hire_date": "2023-12-01"},
    {"staff_no": "OP007", "name": "吴芳",   "role_name": "运维工程师",     "phone": "15812340007", "status": "启用", "hire_date": "2025-07-15"},
    {"staff_no": "OP008", "name": "孙磊",   "role_name": "系统架构师",     "phone": "18812340008", "status": "启用", "hire_date": "2022-11-05"},
    {"staff_no": "OP009", "name": "马丽",   "role_name": "运维工程师",     "phone": "13612340009", "status": "启用", "hire_date": "2025-09-01"},
    {"staff_no": "OP010", "name": "刘洋",   "role_name": "高级运维",       "phone": "15512340010", "status": "启用", "hire_date": "2024-04-18"},
    {"staff_no": "OP011", "name": "黄静",   "role_name": "数据库管理员",   "phone": "13312340011", "status": "启用", "hire_date": "2025-05-12"},
    {"staff_no": "OP012", "name": "林峰",   "role_name": "网络管理员",     "phone": "18912340012", "status": "启用", "hire_date": "2024-09-28"},
    {"staff_no": "OP013", "name": "郑宇",   "role_name": "安全审计员",     "phone": "15612340013", "status": "停用", "hire_date": "2023-06-10"},
    {"staff_no": "OP014", "name": "何慧",   "role_name": "运维工程师",     "phone": "13712340014", "status": "启用", "hire_date": "2026-01-05"},
    {"staff_no": "OP015", "name": "冯超",   "role_name": "运维工程师",     "phone": "18512340015", "status": "启用", "hire_date": "2025-11-20"},
    {"staff_no": "OP016", "name": "韩雪",   "role_name": "系统架构师",     "phone": "13212340016", "status": "启用", "hire_date": "2024-02-14"},
    {"staff_no": "OP017", "name": "曹杰",   "role_name": "高级运维",       "phone": "15912340017", "status": "启用", "hire_date": "2023-10-30"},
    {"staff_no": "OP018", "name": "邓丽",   "role_name": "数据库管理员",   "phone": "18712340018", "status": "启用", "hire_date": "2025-08-08"},
    {"staff_no": "OP019", "name": "彭波",   "role_name": "网络管理员",     "phone": "15212340019", "status": "启用", "hire_date": "2024-07-25"},
    {"staff_no": "OP020", "name": "蒋涛",   "role_name": "安全审计员",     "phone": "13112340020", "status": "启用", "hire_date": "2026-02-01"},
]

# 启用人员列表（用于工单分配）
ACTIVE_STAFF = [s["name"] for s in STAFF if s["status"] == "启用"]

# ──────────────────────────────────────────────
# 3. 工单标题库（真实 IT 运维场景，含中英文）
# ──────────────────────────────────────────────
TICKET_TITLES = [
    # 系统故障类
    "生产环境服务器宕机，业务中断", "核心数据库连接池耗尽", "Redis 集群主从切换失败",
    "Kubernetes Pod 频繁重启", "Nginx 反向代理 502 错误", "消息队列 RabbitMQ 积压严重",
    "Elasticsearch 索引写入阻塞", "负载均衡器健康检查失败", "CDN 回源超时导致页面加载失败",
    "Docker 容器内存溢出 OOM", "Jenkins 构建任务卡死", "GitLab 代码仓库无法拉取",
    "Zabbix 监控告警风暴", "日志收集 Filebeat 断连", "Prometheus 目标抓取超时",
    # 应用故障类
    "用户登录接口返回 401 未授权", "订单支付回调丢失", "报表导出功能报 500 错误",
    "移动端页面白屏无法加载", "短信验证码发送延迟超过 5 分钟", "文件上传接口超时",
    "搜索功能返回空结果", "定时任务未按计划执行", "API 网关限流误触发",
    "第三方支付接口调用失败", "小程序授权登录异常", "数据导出 Excel 格式错误",
    "前端页面渲染卡顿超过 10 秒", "用户权限校验失效", "SSO 单点登录票据过期",
    "WebSocket 推送消息丢失", "PDF 发票生成失败", "批量导入功能数据不完整",
    # 数据库问题
    "数据库死锁导致事务回滚", "慢查询拖慢整体性能", "数据迁移脚本执行失败",
    "主从复制延迟超过 5 秒", "数据库备份任务失败", "表空间不足需要扩容",
    "Oracle 归档日志写满磁盘", "MySQL 主键冲突导致写入失败", "数据同步任务中断",
    # 网络问题
    "办公网络间歇性断网", "VPN 远程连接频繁断开", "防火墙策略误拦截正常流量",
    "DNS 解析异常导致域名无法访问", "内网服务器之间网络延迟高", "无线网络信号弱",
    "专线带宽跑满运营商限速", "交换机端口频繁 Up/Down", "IP 地址冲突",
    # 安全类
    "发现可疑登录尝试", "安全扫描发现高危漏洞", "SSL 证书即将过期需续签",
    "敏感数据未加密存储", "Web 应用防火墙触发误报", "服务器被植入挖矿程序",
    "账号权限越权访问", "数据泄露风险排查", "安全基线检查不合规",
    # 日常运维
    "新员工入职账号开通", "离职员工权限回收", "服务器资源扩容申请",
    "应用版本发布上线", "数据库参数调优", "机房巡检发现温湿度异常",
    "老系统域名到期续费", "监控报警规则调整", "日志归档清理磁盘空间",
    "灾备演练脚本准备", "系统升级维护窗口通知", "第三方服务合同续签审批",
]

# 工单描述模板
TICKET_DESCRIPTIONS = [
    "用户反馈：{}，影响范围：{}，已持续{}小时，需紧急处理。",
    "监控系统告警：{}，告警级别：{}，触发时间：{}，当前状态：待处理。",
    "{}接到用户报修，{}出现异常，初步排查：{}，请协助处理。",
    "巡检发现：{}，上次巡检正常，本次异常时间：{}，建议立即排查。",
    "业务方反馈：{}，涉及{}个用户，{}功能受影响，请尽快修复。",
    "自动化运维平台检测到：{}，触发阈值：{}，当前值：{}，已超过警戒线。",
]


def _gen_description(title: str, priority: str) -> str:
    """根据标题和优先级生成工单描述"""
    templates = TICKET_DESCRIPTIONS
    severity = {"高": "高", "中": "中", "低": "低"}[priority]
    hours = {"高": random.randint(1, 4), "中": random.randint(4, 12), "低": random.randint(12, 48)}[priority]
    users = random.choice(["5-10", "10-50", "50-200", "全部"])
    t = random.choice(templates)
    return t.format(
        title,
        severity,
        hours,
        f"{random.randint(0, 23):02d}:{random.randint(0, 59):02d}",
        random.choice(ACTIVE_STAFF),
        title,
        "网络连接超时 / 服务端口无响应" if random.random() > 0.5 else "日志报错率上升",
        f"{random.randint(0, 23):02d}:{random.randint(0, 59):02d}",
        users,
        random.choice(["登录", "支付", "数据查询", "报表导出"]),
        f"{random.randint(80, 99)}",
        f"{random.randint(100, 999)}",
    )


# ──────────────────────────────────────────────
# 4. 工单数据生成
# ──────────────────────────────────────────────
def generate_tickets(start_date: date, end_date: date) -> list[dict]:
    """
    生成近6个月工单数据
    - 工作日日均 2-5 条，周末日均 0-2 条
    - 月初/月末略多（业务高峰期）
    - 状态/优先级/负责人随机分布
    """
    tickets = []
    current = start_date
    daily_seq: dict[str, int] = {}  # 每日工单序号

    while current <= end_date:
        date_str = current.strftime("%Y%m%d")
        weekday = current.weekday()  # 0=Mon, 6=Sun

        # ── 每日工单数量 ──
        if weekday >= 5:  # 周末
            base_count = random.choices([0, 1, 2], weights=[0.4, 0.4, 0.2])[0]
        else:  # 工作日
            # 月初/月末多 1-2 条
            day_of_month = current.day
            month_end = (current.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
            month_bonus = 0
            if day_of_month <= 3 or day_of_month >= month_end.day - 2:
                month_bonus = random.randint(1, 2)
            base_count = random.randint(2, 5) + month_bonus

        daily_seq[date_str] = 0

        for _ in range(base_count):
            daily_seq[date_str] += 1

            # 生成时间（工作日 8:00-22:00，周末 9:00-20:00）
            if weekday >= 5:
                hour = random.randint(9, 19)
            else:
                # 上午 9-12 和下午 14-18 是高峰
                hour = random.choices(
                    [9, 10, 11, 12, 14, 15, 16, 17, 18, 8, 13, 19, 20, 21],
                    weights=[2, 2, 1.5, 1, 2, 2, 1.5, 1, 0.5, 0.5, 0.5, 0.5, 0.3, 0.2],
                )[0]
            minute = random.randint(0, 59)
            second = random.randint(0, 59)
            create_time = datetime(current.year, current.month, current.day, hour, minute, second)

            # 标题
            title = random.choice(TICKET_TITLES)

            # 优先级分布（高:中:低 ≈ 20:50:30）
            priority = random.choices(["高", "中", "低"], weights=[0.20, 0.50, 0.30])[0]

            # 状态（越老的工单越可能已完成）
            days_ago = (end_date - current).days
            if days_ago > 90:  # 3个月以上
                status = random.choices(["已完成", "进行中", "未完成"], weights=[0.65, 0.15, 0.20])[0]
            elif days_ago > 30:  # 1-3个月
                status = random.choices(["已完成", "进行中", "未完成"], weights=[0.45, 0.25, 0.30])[0]
            elif days_ago > 7:  # 1-4周
                status = random.choices(["已完成", "进行中", "未完成"], weights=[0.30, 0.35, 0.35])[0]
            else:  # 最近一周
                status = random.choices(["已完成", "进行中", "未完成"], weights=[0.15, 0.40, 0.45])[0]

            # 负责人
            assignee = random.choice(ACTIVE_STAFF)

            # 描述
            description = _gen_description(title, priority)

            # updated_at（完成时间比创建时间晚一些）
            if status == "已完成":
                resolve_hours = random.randint(1, 72)
                updated_at = create_time + timedelta(hours=resolve_hours)
            elif status == "进行中":
                updated_at = create_time + timedelta(hours=random.randint(1, 48))
            else:
                updated_at = create_time + timedelta(hours=random.randint(0, 4))

            tickets.append({
                "title": title,
                "status": status,
                "priority": priority,
                "assignee": assignee,
                "create_time": create_time,
                "description": description,
                "updated_at": updated_at,
                "date_str": date_str,
                "seq": daily_seq[date_str],
            })

        current += timedelta(days=1)

    # 按创建时间排序
    tickets.sort(key=lambda t: t["create_time"])

    # 为每个工单分配 TKT-YYYYMMDD-XXXX 格式 ID
    date_seq: dict[str, int] = {}
    for t in tickets:
        ds = t["date_str"]
        date_seq[ds] = date_seq.get(ds, 0) + 1
        t["id"] = f"TKT-{ds}-{date_seq[ds]:04d}"

    return tickets


# ──────────────────────────────────────────────
# 5. 排班数据生成
# ──────────────────────────────────────────────
def generate_schedule(start_date: date, end_date: date) -> list[dict]:
    """
    生成排班数据：每人每天一个班次（早班/下午班/晚班/休息）
    18 人分 4 组，每周轮转，均匀分配
    """
    schedules = []
    shift_types = ["早班", "下午班", "晚班", "休息"]
    names = ACTIVE_STAFF  # 18 人

    # 18 人分 4 组：G0(0-4)=5人, G1(5-9)=5人, G2(10-13)=4人, G3(14-17)=4人
    def group_of(idx: int) -> int:
        if idx < 5: return 0
        if idx < 10: return 1
        if idx < 14: return 2
        return 3

    current = start_date
    while current <= end_date:
        # 计算当前日期是本年第几周（ISO 周），用这周的偏移量来轮转
        iso = current.isocalendar()
        week_num = iso[1]  # 1-53
        week_offset = week_num % 4

        for idx, name in enumerate(names):
            g = group_of(idx)
            shift_idx = (g + week_offset) % 4
            st = shift_types[shift_idx]
            schedules.append({
                "staff_name": name,
                "shift_date": current.isoformat(),
                "shift_type": st,
            })
        current += timedelta(days=1)

    return schedules


# ──────────────────────────────────────────────
# 6. 工单流转历史生成
# ──────────────────────────────────────────────
def generate_ticket_history(tickets: list[dict]) -> list[dict]:
    """为每个工单生成 1-3 条流转记录"""
    history = []
    actions = [
        ("创建工单", None, None),
        ("变更优先级", None, None),
        ("转派负责人", None, None),
        ("开始处理", None, None),
        ("添加备注", None, None),
        ("标记已完成", None, None),
        ("修改描述", None, None),
    ]
    operators = ACTIVE_STAFF + ["系统"]

    for t in tickets:
        # 至少一条"创建工单"记录
        history.append({
            "ticket_id": t["id"],
            "action": "创建工单",
            "operator": t["assignee"],
            "old_value": "",
            "new_value": t["status"],
            "remark": f"工单创建：{t['title']}",
            "created_at": t["create_time"],
        })

        # 额外 0-2 条流转记录
        for _ in range(random.randint(0, 2)):
            action, old_val, new_val = random.choice(actions[1:])  # 跳过"创建工单"
            op = random.choice(operators)
            act_time = t["create_time"] + timedelta(hours=random.randint(1, 48))
            if act_time > t["updated_at"]:
                act_time = t["updated_at"]
            history.append({
                "ticket_id": t["id"],
                "action": action,
                "operator": op,
                "old_value": old_val or "",
                "new_value": new_val or "",
                "remark": random.choice(["", "按流程处理", "经确认后操作", "用户已确认"]),
                "created_at": act_time,
            })

    return history


# ──────────────────────────────────────────────
# 7. 统计汇总
# ──────────────────────────────────────────────
def print_summary(tickets: list[dict], schedules: list[dict]):
    """打印数据生成统计"""
    total = len(tickets)
    status_dist = {}
    priority_dist = {}
    assignee_dist = {}
    for t in tickets:
        status_dist[t["status"]] = status_dist.get(t["status"], 0) + 1
        priority_dist[t["priority"]] = priority_dist.get(t["priority"], 0) + 1
        assignee_dist[t["assignee"]] = assignee_dist.get(t["assignee"], 0) + 1

    print("=" * 60)
    print(f"  数据生成统计")
    print("=" * 60)
    print(f"  工单总数: {total}")
    print(f"  状态分布: {status_dist}")
    print(f"  优先级分布: {priority_dist}")
    print(f"  人员数量: {len(STAFF)} (启用: {len(ACTIVE_STAFF)})")
    print(f"  排班记录: {len(schedules)}")
    print(f"  时间范围: {tickets[0]['create_time'].strftime('%Y-%m-%d')} ~ {tickets[-1]['create_time'].strftime('%Y-%m-%d')}")
    print(f"  负责人分布:")
    for name, count in sorted(assignee_dist.items(), key=lambda x: -x[1]):
        bar = "█" * (count // 5)
        print(f"    {name:6s}: {count:3d} {bar}")
    print("=" * 60)


# ──────────────────────────────────────────────
# 8. 主入口
# ──────────────────────────────────────────────
if __name__ == "__main__":
    # 时间范围：2026-02-01 ~ 2026-07-26（6个完整自然月）
    START = date(2026, 2, 1)
    END = date(2026, 7, 26)

    print("正在生成工单数据...")
    tickets = generate_tickets(START, END)
    print(f"工单生成完成: {len(tickets)} 条")

    print("正在生成排班数据...")
    schedules = generate_schedule(START, END)
    print(f"排班生成完成: {len(schedules)} 条")

    print("正在生成流转历史...")
    history = generate_ticket_history(tickets)
    print(f"流转历史生成完成: {len(history)} 条")

    print_summary(tickets, schedules)

    print("\n✅ 数据生成完毕。请运行 seed_all() 导入数据库。")