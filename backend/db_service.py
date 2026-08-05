"""
数据库服务模块
连接 SQL Server（离线部署），管理工单和监控数据

连接策略：连接池（queue.Queue）+ pyodbc 连接池复用。
每个请求从池中借用连接，请求结束后归还，避免每次请求创建新连接
导致 SQL Server 连接数暴涨和频繁断连。
"""
import pyodbc
import random
import threading
import time
import hashlib
from datetime import datetime, timedelta
from queue import Queue, Empty, Full
from mock_data import TICKETS, SERVERS_METRICS
from seed_data_v2 import (
    ROLES, STAFF, ACTIVE_STAFF, TICKET_TITLES,
    generate_tickets, generate_schedule, generate_ticket_history,
)

# ========== ODBC 连接池（驱动层复用） ==========
pyodbc.pooling = True

# ========== 数据库配置 ==========
DB_CONFIG = {
    'server': '127.0.0.1',
    'database': 'OpsCenter',
    'username': 'ai_ops_user',
    'password': 'Ops1234',
    'driver': '{ODBC Driver 17 for SQL Server}',
    'encrypt': 'yes',
    'trust_server_certificate': 'yes'
}

# ========== 连接池配置 ==========
POOL_SIZE = 8          # 固定连接数（足够处理并发请求，不过度占用 SQL Server 资源）
POOL_TIMEOUT = 5       # 获取连接的超时秒数
RETRY_COUNT = 3        # 连接失败重试次数
RETRY_DELAY = 0.5      # 重试间隔秒数

# 连接池：存放可用连接
_pool: Queue = None
_pool_lock = threading.Lock()

# 线程本地：记录当前线程借用的连接引用（用于归还）
_local = threading.local()


def _fmt_time(dt) -> str:
    """将 datetime 格式化为 YYYY-MM-DD HH:MM:SS 字符串"""
    if dt is None:
        return ""
    if hasattr(dt, 'strftime'):
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return str(dt)


def _create_connection():
    """创建一个新的数据库连接（带重试）"""
    conn_str = get_connection_string()
    last_error = None
    for attempt in range(1, RETRY_COUNT + 1):
        try:
            conn = pyodbc.connect(conn_str, timeout=10)
            conn.autocommit = True
            return conn
        except pyodbc.Error as e:
            last_error = e
            if attempt < RETRY_COUNT:
                time.sleep(RETRY_DELAY * attempt)
    raise last_error


def _init_pool():
    """初始化连接池（懒加载，首次调用 get_connection 时触发）"""
    global _pool
    with _pool_lock:
        if _pool is not None:
            return
        _pool = Queue(maxsize=POOL_SIZE)
        created = 0
        for i in range(POOL_SIZE):
            try:
                conn = _create_connection()
                _pool.put(conn)
                created += 1
            except Exception as e:
                print(f"[DB] ⚠️ 连接池预创建第 {i+1} 个连接失败: {e}")
        print(f"[DB] [连接池] 初始化完成: {created}/{POOL_SIZE} 个连接就绪")


def _is_connection_valid(conn) -> bool:
    """快速检查连接是否有效"""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        return True
    except pyodbc.Error:
        return False


def get_connection_string() -> str:
    return (
        f"DRIVER={DB_CONFIG['driver']};"
        f"SERVER={DB_CONFIG['server']};"
        f"DATABASE={DB_CONFIG['database']};"
        f"UID={DB_CONFIG['username']};"
        f"PWD={DB_CONFIG['password']};"
        f"Encrypt={DB_CONFIG['encrypt']};"
        f"TrustServerCertificate={DB_CONFIG['trust_server_certificate']};"
    )


def get_connection():
    """
    从连接池借用连接。
    - 同一请求内多次调用复用同一个连接（通过 _local.borrowed）
    - 新请求首次调用时从池中取一个连接
    - 若池中无可用连接，阻塞等待最多 POOL_TIMEOUT 秒
    - 连接失效时自动重建
    """
    # 同一请求内复用已借用的连接
    borrowed = getattr(_local, 'borrowed', None)
    if borrowed is not None:
        if _is_connection_valid(borrowed):
            return borrowed
        # 连接失效，清理后重新借
        try:
            borrowed.close()
        except Exception:
            pass
        _local.borrowed = None

    # 确保池已初始化
    _init_pool()

    # 从池中取连接（带超时和重试）
    for attempt in range(1, RETRY_COUNT + 1):
        try:
            conn = _pool.get(timeout=POOL_TIMEOUT)
            if _is_connection_valid(conn):
                _local.borrowed = conn
                return conn
            # 连接失效，丢弃并重建
            try:
                conn.close()
            except Exception:
                pass
            conn = _create_connection()
            _local.borrowed = conn
            return conn
        except Empty:
            if attempt < RETRY_COUNT:
                time.sleep(RETRY_DELAY * attempt)
            continue
        except pyodbc.Error as e:
            if attempt < RETRY_COUNT:
                time.sleep(RETRY_DELAY * attempt)
            else:
                raise

    raise Exception(f"[DB] 连接池已满，{POOL_TIMEOUT}s 内无可用连接")


def return_connection():
    """
    归还当前线程借用的连接到池中。
    由 Flask @app.teardown_request 在每个请求结束后自动调用。
    """
    borrowed = getattr(_local, 'borrowed', None)
    if borrowed is None:
        return
    _local.borrowed = None
    try:
        if _is_connection_valid(borrowed):
            try:
                _pool.put_nowait(borrowed)
            except Full:
                # 池满了（异常情况），关闭多余连接
                try:
                    borrowed.close()
                except Exception:
                    pass
            return
    except Exception:
        pass
    # 连接已失效，关闭并补充新连接
    try:
        borrowed.close()
    except Exception:
        pass
    try:
        new_conn = _create_connection()
        try:
            _pool.put_nowait(new_conn)
        except Full:
            new_conn.close()
    except Exception as e:
        print(f"[DB] ⚠️ 补充连接失败: {e}")


def close_all():
    """关闭连接池中的所有连接（应用退出时调用）"""
    global _pool
    if _pool is None:
        return
    closed = 0
    while True:
        try:
            conn = _pool.get_nowait()
            try:
                conn.close()
                closed += 1
            except Exception:
                pass
        except Empty:
            break
    _pool = None
    print(f"[DB] [连接池] 已关闭，共关闭 {closed} 个连接")


# ========== 建表 ==========
def init_database():
    conn = get_connection()
    cursor = conn.cursor()
    print("[DB] 正在创建表...")

    cursor.execute("""
    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='tickets' AND xtype='U')
    CREATE TABLE tickets (
        id INT PRIMARY KEY,
        title NVARCHAR(200) NOT NULL,
        status NVARCHAR(20) NOT NULL,
        priority NVARCHAR(10) NOT NULL,
        create_time DATETIME2 NOT NULL,
        assignee NVARCHAR(50) NOT NULL,
        description NVARCHAR(MAX),
        updated_at DATETIME2 DEFAULT GETDATE()
    )""")

    # 迁移：为已存在的 tickets 表补加 description 列
    try:
        cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('tickets') AND name = 'description')
        ALTER TABLE tickets ADD description NVARCHAR(MAX)
        """)
        print("[DB] ✅ tickets.description 列已添加")
    except Exception as e:
        print(f"[DB] ⚠️ 添加 description 列失败（如已存在则忽略）: {e}")

    # 迁移：为已存在的 tickets 表补加 updated_at 列（兼容旧表结构）
    try:
        cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('tickets') AND name = 'updated_at')
        ALTER TABLE tickets ADD updated_at DATETIME2 DEFAULT GETDATE()
        """)
    except Exception as e:
        print(f"[DB] ⚠️ 添加 updated_at 列失败（如已存在则忽略）: {e}")

    cursor.execute("""
    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='metrics_snapshots' AND xtype='U')
    CREATE TABLE metrics_snapshots (
        id INT IDENTITY(1,1) PRIMARY KEY,
        cpu_usage_percent FLOAT,
        memory_usage_percent FLOAT,
        disk_usage_percent FLOAT,
        network_in_mbps FLOAT,
        network_out_mbps FLOAT,
        disk_read_mbps FLOAT,
        disk_write_mbps FLOAT,
        snapshot_time DATETIME2 DEFAULT GETDATE()
    )""")

    cursor.execute("""
    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='sys_config' AND xtype='U')
    CREATE TABLE sys_config (
        config_key NVARCHAR(50) PRIMARY KEY,
        config_value NVARCHAR(100) NOT NULL,
        updated_at DATETIME2 DEFAULT GETDATE()
    )""")

    cursor.execute("""
    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='staff_roles' AND xtype='U')
    CREATE TABLE staff_roles (
        role_id INT IDENTITY(1,1) PRIMARY KEY,
        role_name NVARCHAR(50) NOT NULL,
        tag_id INT NULL,
        created_at DATETIME2 DEFAULT GETDATE()
    )""")

    # 迁移：staff_roles 补加 tag_id 列
    try:
        cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('staff_roles') AND name = 'tag_id')
        ALTER TABLE staff_roles ADD tag_id INT NULL
        """)
        print("[DB] ✅ staff_roles.tag_id 列已添加")
    except Exception as e:
        print(f"[DB] ⚠️ 添加 tag_id 列失败（如已存在则忽略）: {e}")

    # 角色标签表
    cursor.execute("""
    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='role_tags' AND xtype='U')
    CREATE TABLE role_tags (
        tag_id INT IDENTITY(1,1) PRIMARY KEY,
        tag_name NVARCHAR(50) NOT NULL,
        tag_color NVARCHAR(7) DEFAULT '#3b82f6',
        created_at DATETIME2 DEFAULT GETDATE()
    )""")

    # 员工-标签关联表（每个员工可关联多个标签）
    cursor.execute("""
    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='staff_tags' AND xtype='U')
    CREATE TABLE staff_tags (
        id INT IDENTITY(1,1) PRIMARY KEY,
        staff_id INT NOT NULL,
        tag_id INT NOT NULL,
        created_at DATETIME2 DEFAULT GETDATE(),
        CONSTRAINT UQ_staff_tag UNIQUE (staff_id, tag_id),
        FOREIGN KEY (staff_id) REFERENCES staff(id),
        FOREIGN KEY (tag_id) REFERENCES role_tags(tag_id)
    )""")

    # 角色-标签关联表（每个角色可关联多个标签）
    cursor.execute("""
    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='role_tag_rel' AND xtype='U')
    CREATE TABLE role_tag_rel (
        id INT IDENTITY(1,1) PRIMARY KEY,
        role_id INT NOT NULL,
        tag_id INT NOT NULL,
        created_at DATETIME2 DEFAULT GETDATE(),
        CONSTRAINT UQ_role_tag UNIQUE (role_id, tag_id),
        FOREIGN KEY (role_id) REFERENCES staff_roles(role_id),
        FOREIGN KEY (tag_id) REFERENCES role_tags(tag_id)
    )""")

    cursor.execute("""
    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='staff' AND xtype='U')
    CREATE TABLE staff (
        id INT IDENTITY(1,1) PRIMARY KEY,
        staff_no NVARCHAR(20) NOT NULL UNIQUE,
        name NVARCHAR(50) NOT NULL,
        role_id INT NULL,
        phone NVARCHAR(20) NOT NULL,
        password_hash NVARCHAR(64) DEFAULT 'e10adc3949ba59abbe56e057f20f883e',
        status NVARCHAR(10) DEFAULT '启用',
        created_at DATETIME2 DEFAULT GETDATE(),
        FOREIGN KEY (role_id) REFERENCES staff_roles(role_id)
    )""")

    cursor.execute("""
    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='staff_schedule' AND xtype='U')
    CREATE TABLE staff_schedule (
        schedule_id INT IDENTITY(1,1) PRIMARY KEY,
        staff_name NVARCHAR(50) NOT NULL,
        shift_date DATE NOT NULL,
        shift_type NVARCHAR(20) NOT NULL,
        created_at DATETIME2 DEFAULT GETDATE()
    )""")

    cursor.execute("""
    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='ticket_history' AND xtype='U')
    CREATE TABLE ticket_history (
        id INT IDENTITY(1,1) PRIMARY KEY,
        ticket_id INT NOT NULL,
        action NVARCHAR(50) NOT NULL,
        operator NVARCHAR(50) NOT NULL,
        old_value NVARCHAR(50),
        new_value NVARCHAR(50),
        remark NVARCHAR(500),
        created_at DATETIME2 DEFAULT GETDATE()
    )""")
    # 迁移：tickets.id INT → NVARCHAR(30)（支持 TKT-YYYYMMDD-XXXX 格式）
    # SQL Server 不允许直接 ALTER 带 PK 的列类型，需先删 PK 再重建
    try:
        cursor.execute("SELECT DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='tickets' AND COLUMN_NAME='id'")
        row = cursor.fetchone()
        if row and row[0] == 'int':
            # 动态删除主键约束
            cursor.execute("""
                DECLARE @pk_name NVARCHAR(128);
                SELECT @pk_name = name FROM sys.key_constraints
                WHERE type = 'PK' AND parent_object_id = OBJECT_ID('tickets');
                IF @pk_name IS NOT NULL
                BEGIN
                    DECLARE @sql NVARCHAR(MAX) = 'ALTER TABLE tickets DROP CONSTRAINT ' + @pk_name;
                    EXEC sp_executesql @sql;
                END
            """)
            cursor.execute("ALTER TABLE tickets ALTER COLUMN id NVARCHAR(30) NOT NULL")
            cursor.execute("ALTER TABLE tickets ADD CONSTRAINT PK_tickets PRIMARY KEY (id)")
            print("[DB] ✅ tickets.id 已迁移为 NVARCHAR(30) (已重建PK)")
    except Exception as e:
        print(f"[DB] ⚠️ tickets.id 迁移（如已迁移则忽略）: {e}")

    # 迁移：ticket_history.ticket_id INT → NVARCHAR(30)
    try:
        cursor.execute("SELECT DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='ticket_history' AND COLUMN_NAME='ticket_id'")
        row = cursor.fetchone()
        if row and row[0] == 'int':
            cursor.execute("ALTER TABLE ticket_history ALTER COLUMN ticket_id NVARCHAR(30) NOT NULL")
            print("[DB] ✅ ticket_history.ticket_id 已迁移为 NVARCHAR(30)")
    except Exception as e:
        print(f"[DB] ⚠️ ticket_history.ticket_id 迁移（如已迁移则忽略）: {e}")

    # 迁移：将旧整数/短格式的工单 ID 更新为 TKT-YYYYMMDD-XXXX 格式
    try:
        # 匹配两种格式：纯数字 和 TKT-XX 短格式（含 TKT- 但长度不足14）
        cursor.execute("""
            SELECT id, create_time FROM tickets 
            WHERE id NOT LIKE 'TKT-________-____%' OR LEN(id) < 14
            ORDER BY create_time
        """)
        rows = cursor.fetchall()
        if rows:
            daily_seq: dict[str, int] = {}
            for old_id, create_time in rows:
                if create_time:
                    date_str = create_time.strftime("%Y%m%d") if hasattr(create_time, 'strftime') else datetime.utcnow().strftime("%Y%m%d")
                else:
                    date_str = datetime.utcnow().strftime("%Y%m%d")
                daily_seq[date_str] = daily_seq.get(date_str, 0) + 1
                new_id = f"TKT-{date_str}-{daily_seq[date_str]:04d}"
                cursor.execute("UPDATE tickets SET id = ? WHERE id = ?", new_id, str(old_id))
                cursor.execute("UPDATE ticket_history SET ticket_id = ? WHERE ticket_id = ?", new_id, str(old_id))
                print(f"[DB] 工单 ID: {old_id} → {new_id}")
            print(f"[DB] ✅ 迁移了 {len(rows)} 个旧工单 ID 为 TKT-YYYYMMDD-XXXX 格式")
    except Exception as e:
        print(f"[DB] ⚠️ 工单 ID 格式迁移（如已完成则忽略）: {e}")

    print("[DB] ✅ 表已就绪")


# ========== 导入 Mock 数据 ==========
def seed_tickets():
    """导入近6个月工单数据（覆盖旧数据）"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tickets")
    cursor.execute("DELETE FROM ticket_history")

    from datetime import date as _date
    START = _date(2026, 2, 1)
    END = _date.today()

    print(f"[DB] 正在生成 {START} ~ {END} 工单数据...")
    tickets = generate_tickets(START, END)
    print(f"[DB] 生成工单 {len(tickets)} 条")

    sql = "INSERT INTO tickets (id, title, status, priority, create_time, assignee, description, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
    count = 0
    for t in tickets:
        try:
            cursor.execute(sql, (
                t["id"], t["title"], t["status"], t["priority"],
                t["create_time"], t["assignee"], t["description"], t["updated_at"]
            ))
            count += 1
        except Exception as e:
            print(f"[DB] ⚠️ 工单 {t['id']} 失败: {e}")

    print(f"[DB] ✅ 已导入 {count}/{len(tickets)} 条工单")

    # 导入流转历史
    print(f"[DB] 正在生成流转历史...")
    history = generate_ticket_history(tickets)
    h_sql = "INSERT INTO ticket_history (ticket_id, action, operator, old_value, new_value, remark, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)"
    h_count = 0
    for h in history:
        try:
            cursor.execute(h_sql, (
                h["ticket_id"], h["action"], h["operator"],
                h["old_value"], h["new_value"], h["remark"], h["created_at"]
            ))
            h_count += 1
        except Exception as e:
            print(f"[DB] ⚠️ 流转历史 {h['ticket_id']} 失败: {e}")
    print(f"[DB] ✅ 已导入 {h_count}/{len(history)} 条流转历史")


def seed_metrics():
    """生成并导入 200 条历史监控快照数据（随机游走模拟，覆盖约30天）"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM metrics_snapshots")

    m = SERVERS_METRICS
    # 从 mock_data 提取基准值
    base = m["metrics"] if "metrics" in m else m
    now = datetime.utcnow()

    # 从基准值出发，用随机游走生成 200 条，覆盖约 30 天
    cpu = base.get("cpu_usage_percent", 45)
    mem = base.get("memory_usage_percent", 55)
    disk_r = base.get("disk_read_mbps", 30)
    disk_w = base.get("disk_write_mbps", 20)
    net_in = base.get("network_in_mbps", 100)
    net_out = base.get("network_out_mbps", 80)

    for i in range(200):
        snapshot_time = now - timedelta(days=30) + timedelta(minutes=i * 216)  # ~每3.6h一个点

        # 随机游走 + 周期性波动（降低上限避免恒100%问题）
        cpu = max(10, min(92, cpu + random.uniform(-3, 3) + 5 * __import__('math').sin(i * 0.15)))
        mem = max(20, min(88, mem + random.uniform(-2, 2) + 3 * __import__('math').sin(i * 0.1 + 1)))
        disk_r = max(0, disk_r + random.uniform(-5, 5) + 8 * __import__('math').sin(i * 0.12))
        disk_w = max(0, disk_w + random.uniform(-3, 3) + 4 * __import__('math').sin(i * 0.08 + 2))
        net_in = max(0, net_in + random.uniform(-10, 10) + 12 * __import__('math').sin(i * 0.2))
        net_out = max(0, net_out + random.uniform(-8, 8) + 10 * __import__('math').sin(i * 0.18 + 0.5))

        cursor.execute("""
            INSERT INTO metrics_snapshots
            (cpu_usage_percent, memory_usage_percent, disk_usage_percent,
             network_in_mbps, network_out_mbps, disk_read_mbps, disk_write_mbps, snapshot_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (round(cpu, 1), round(mem, 1),
              round(base.get("disk_usage_percent", 60), 1),
              round(net_in, 1),
              round(net_out, 1),
              round(disk_r, 1),
              round(disk_w, 1),
              snapshot_time))

    print("[DB] ✅ 200 条历史监控快照已导入（30天随机游走）")


# ========== 查询接口 ==========

def _fmt_tid(raw_id) -> str:
    """格式化工单 ID 为 TKT-YYYYMMDD-XXXX 统一格式，兼容 DB 中旧纯数字 ID 和 TKT-XX 短格式"""
    s = str(raw_id).strip()
    # 已经是完整格式 TKT-YYYYMMDD-XXXX（至少14字符）
    if s.startswith("TKT-") and len(s) >= 14:
        return s
    # 提取纯数字部分
    if s.startswith("TKT-"):
        num_part = s[4:]
    else:
        num_part = s
    try:
        n = int(num_part)
    except ValueError:
        return s  # 无法解析，原样返回
    # 用今天日期生成完整格式，同时保留原始序号
    today = datetime.utcnow().strftime("%Y%m%d")
    return f"TKT-{today}-{n:04d}"


def get_tickets(status: str = None, priority: str = None) -> list:
    conn = get_connection()
    cursor = conn.cursor()
    if status and priority:
        cursor.execute("SELECT id, title, status, priority, create_time, assignee, description FROM tickets WHERE status = ? AND priority = ? ORDER BY id", status, priority)
    elif status:
        cursor.execute("SELECT id, title, status, priority, create_time, assignee, description FROM tickets WHERE status = ? ORDER BY id", status)
    elif priority:
        cursor.execute("SELECT id, title, status, priority, create_time, assignee, description FROM tickets WHERE priority = ? ORDER BY id", priority)
    else:
        cursor.execute("SELECT id, title, status, priority, create_time, assignee, description FROM tickets ORDER BY id")
    return [{"id": _fmt_tid(r[0]), "title": r[1], "status": r[2], "priority": r[3],
             "create_time": _fmt_time(r[4]), "assignee": r[5], "description": r[6]} for r in cursor.fetchall()]


def get_tickets_page(
    page: int = 1,
    limit: int = 10,
    keyword: str = None,
    status: str = None,
    priority: str = None,
    assignee: str = None,
    date_start: str = None,
    date_end: str = None,
) -> dict:
    """
    多条件分页查询工单（前端工单列表页使用）
    所有过滤条件都可空；空时走"全部"路径
    date_start / date_end: YYYY-MM-DD 格式，按 create_time 列过滤
    返回：{"data": [tickets...], "total": N, "page": p, "limit": l, "total_pages": tp}
    """
    # 1) 动态 SQL：WHERE 1=1 起步 + 参数化（pyodbc 风格 ? 占位）
    where_sql = " WHERE 1=1"
    sql_params = []
    if status and status != "全部":
        where_sql += " AND status = ?"
        sql_params.append(status)
    if priority and priority != "全部":
        where_sql += " AND priority = ?"
        sql_params.append(priority)
    if assignee and assignee != "全部":
        where_sql += " AND assignee = ?"
        sql_params.append(assignee)
    if date_start:
        where_sql += " AND create_time >= ?"
        sql_params.append(date_start.strip())
    if date_end:
        where_sql += " AND create_time <= ?"
        sql_params.append(date_end.strip() + " 23:59:59")
    if keyword:
        # 关键词同时模糊匹配 title / description（缺 desc 则仅 title）
        where_sql += " AND (title LIKE ? OR description LIKE ?)"
        kw = f"%{keyword.strip()}%"
        sql_params.append(kw)
        sql_params.append(kw)

    conn = get_connection()
    cursor = conn.cursor()
    try:
        # 2) 先 COUNT
        cursor.execute(f"SELECT COUNT(*) FROM tickets{where_sql}", sql_params)
        total = cursor.fetchone()[0]
    except Exception:
        # 兜底：万一 description 字段不存在，回退到只匹配 title
        if keyword:
            where_sql2 = where_sql.replace(
                " AND (title LIKE ? OR description LIKE ?)", " AND title LIKE ?"
            )
            cursor.execute(f"SELECT COUNT(*) FROM tickets{where_sql2}", sql_params[:1])
            total = cursor.fetchone()[0]
            where_sql = where_sql2
        else:
            raise

    # 3) 分页（pyodbc 不支持 LIMIT/OFFSET，用 TOP + 子查询）
    try:
        page = max(1, int(page))
        limit = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        page, limit = 1, 10
    offset = (page - 1) * limit
    if offset == 0:
        cursor.execute(
            f"SELECT id, title, status, priority, create_time, assignee, description FROM tickets{where_sql} ORDER BY id DESC OFFSET 0 ROWS FETCH NEXT ? ROWS ONLY",
            sql_params + [limit],
        )
    else:
        cursor.execute(
            f"SELECT id, title, status, priority, create_time, assignee, description FROM tickets{where_sql} ORDER BY id DESC OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",
            sql_params + [offset, limit],
        )
    rows = cursor.fetchall()
    items = [
        {"id": _fmt_tid(r[0]), "title": r[1], "status": r[2], "priority": r[3],
         "create_time": _fmt_time(r[4]) if r[4] else "",
         "assignee": r[5], "description": r[6]}
        for r in rows
    ]
    cursor.close()
    return {
        "data": items,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": (total + limit - 1) // limit,
    }


def get_ticket_by_id(tid) -> dict:
    tid = str(tid).strip() if tid is not None else ""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, status, priority, create_time, assignee, description FROM tickets WHERE id = ?", tid)
    r = cursor.fetchone()
    if not r:
        return None
    return {"id": _fmt_tid(r[0]), "title": r[1], "status": r[2], "priority": r[3],
            "create_time": _fmt_time(r[4]), "assignee": r[5], "description": r[6]}


def delete_ticket(tid) -> dict:
    """
    删除工单。返回结构化结果，便于上层做精细提示。
    成功：{"ok": True, "id": tid, "title": str}
    失败：
      - 工单不存在：{"ok": False, "id": tid, "reason": "not_found"}
      - DB 错误    ：{"ok": False, "id": tid, "reason": "db_error", "error": str}
      - 参数非法   ：{"ok": False, "id": tid, "reason": "invalid_id"}
    """
    # 1) 参数校验
    tid = str(tid).strip() if tid else ""
    if not tid:
        return {"ok": False, "id": tid, "reason": "invalid_id"}

    # 2) 先查存在（同时拿到 title/status 用于判断）
    ticket = get_ticket_by_id(tid)
    if not ticket:
        return {"ok": False, "id": tid, "reason": "not_found"}

    # 3) 状态检查：只能删除未完成或已完成的工单（进行中不可删除）
    if ticket["status"] == "进行中":
        return {"ok": False, "id": tid, "reason": "进行中的工单不可删除"}

    # 4) 执行删除
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM tickets WHERE id = ?", tid)
        conn.commit()
        return {"ok": True, "id": tid, "title": ticket["title"]}
    except Exception as e:
        # 任何 DB 错误都安全回滚（pyodbc 在出错时通常自动回滚，但显式 rollback 更稳）
        try:
            conn.rollback()
        except Exception:
            pass
        return {"ok": False, "id": tid, "reason": "db_error", "error": str(e)}


# ============== 多条件动态搜索 ==============
# 6 类参数：ticket_id / assignee / status / priority / keyword / start_date / end_date
# 全部走参数化查询（pyodbc 风格 ? 占位符），杜绝 SQL 注入
# 设计原则：
#   1) 用 WHERE 1=1 起步，按需 append AND ... = ?
#   2) 关键词同时模糊匹配 title/description，无 description 字段则仅查 title
#   3) end_date 加 23:59:59 包含当天
#   4) 返回格式与 get_tickets 完全一致

def _tickets_table_has_description(cursor) -> bool:
    """探测 tickets 表是否包含 description 列，缺失则只查 title"""
    try:
        cursor.execute(
            "SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_NAME = 'tickets' AND COLUMN_NAME = 'description'"
        )
        return cursor.fetchone() is not None
    except Exception:
        return False


def search_tickets_dynamic(params: dict) -> dict:
    """
    多条件动态搜索工单（支持 6 类参数自由组合）
    params 允许的键（均为可选）：
      - ticket_id   : int
      - assignee    : str   （姓名精确匹配）
      - status      : str   （未完成 / 进行中 / 已完成）
      - priority    : str   （高 / 中 / 低）
      - keyword     : str   （标题 / 描述模糊匹配）
      - start_date  : str   （YYYY-MM-DD 包含当天）
      - end_date    : str   （YYYY-MM-DD 包含当天 → 加 23:59:59）
    返回：
      {"tickets": [...], "total": N, "applied_filters": {...实际用到的过滤器...}}
    """
    if not isinstance(params, dict):
        params = {}

    conn = get_connection()
    cursor = conn.cursor()

    # 0) 探测 description 字段是否存在（缺则降级为只查 title）
    has_desc = _tickets_table_has_description(cursor)

    # 1) 动态 SQL 生成器（WHERE 1=1 + 追加 AND ... = ?）
    sql = "SELECT id, title, status, priority, create_time, assignee, description FROM tickets WHERE 1=1"
    sql_params = []
    applied = {}

    # 工单 ID
    if params.get("ticket_id") not in (None, "", 0):
        try:
            sql += " AND id = ?"
            sql_params.append(int(params["ticket_id"]))
            applied["ticket_id"] = int(params["ticket_id"])
        except (TypeError, ValueError):
            pass

    # 负责人
    if params.get("assignee"):
        sql += " AND assignee = ?"
        sql_params.append(str(params["assignee"]).strip())
        applied["assignee"] = str(params["assignee"]).strip()

    # 状态
    if params.get("status"):
        sql += " AND status = ?"
        sql_params.append(str(params["status"]).strip())
        applied["status"] = str(params["status"]).strip()

    # 优先级
    if params.get("priority"):
        sql += " AND priority = ?"
        sql_params.append(str(params["priority"]).strip())
        applied["priority"] = str(params["priority"]).strip()

    # 关键词模糊
    if params.get("keyword"):
        kw = f"%{str(params['keyword']).strip()}%"
        if has_desc:
            sql += " AND (title LIKE ? OR description LIKE ?)"
            sql_params.append(kw)
            sql_params.append(kw)
        else:
            sql += " AND title LIKE ?"
            sql_params.append(kw)
        applied["keyword"] = str(params["keyword"]).strip()

    # 起始时间（含当天）
    if params.get("start_date"):
        sql += " AND create_time >= ?"
        sql_params.append(str(params["start_date"]).strip())
        applied["start_date"] = str(params["start_date"]).strip()

    # 结束时间（含当天 → 加 23:59:59）
    if params.get("end_date"):
        sql += " AND create_time <= ?"
        sql_params.append(str(params["end_date"]).strip() + " 23:59:59")
        applied["end_date"] = str(params["end_date"]).strip()

    # 2) 执行 + 转换
    cursor.execute(sql, sql_params)
    rows = cursor.fetchall()
    tickets = [
        {"id": _fmt_tid(r[0]), "title": r[1], "status": r[2], "priority": r[3],
         "create_time": _fmt_time(r[4]) if r[4] else "",
         "assignee": r[5], "description": r[6]}
        for r in rows
    ]
    cursor.close()
    return {"tickets": tickets, "total": len(tickets), "applied_filters": applied}


def get_tickets_stat(start_date=None, end_date=None) -> dict:
    """
    工单状态统计（可选时间范围过滤）
    Args:
        start_date: 起始日期，字符串 "YYYY-MM-DD"（含），按 create_time 过滤
        end_date:   结束日期，字符串 "YYYY-MM-DD"（含），按 create_time 过滤；为方便用户
                    口头表达"今天之前"，把当天 23:59:59 作为截止点
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 动态拼 where 条件（参数化查询防 SQL 注入）
    where_clauses = []
    where_params = []
    if start_date:
        where_clauses.append("create_time >= ?")
        where_params.append(start_date)
    if end_date:
        where_clauses.append("create_time <= ?")
        where_params.append(end_date + " 23:59:59")
    where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    cursor.execute(f"SELECT COUNT(*) FROM tickets{where_sql}", where_params)
    total = cursor.fetchone()[0]
    cursor.execute(f"SELECT status, COUNT(*) FROM tickets{where_sql} GROUP BY status", where_params)
    sc = {r[0]: r[1] for r in cursor.fetchall()}
    cursor.execute(f"SELECT priority, COUNT(*) FROM tickets{where_sql} GROUP BY priority", where_params)
    pc = {r[0]: r[1] for r in cursor.fetchall()}
    cursor.execute(f"SELECT assignee, COUNT(*) FROM tickets{where_sql} GROUP BY assignee", where_params)
    ac = {r[0]: r[1] for r in cursor.fetchall()}

    return {
        "total": total,
        "status_distribution": sc,
        "priority_distribution": pc,
        "assignee_distribution": ac,
        "filter": {
            "start_date": start_date,
            "end_date": end_date,
        },
    }


def get_tickets_report(start_date: str, end_date: str) -> dict:
    """
    工单趋势报告专用查询：取一段时间内的多维度数据，供 LLM 总结报告。
    返回结构：
    {
      "filter": {"start_date":.., "end_date":.., "days": N},
      "total": int,
      "status_distribution": {"未完成":x, "进行中":x, "已完成":x},
      "priority_distribution": {"高":x, "中":x, "低":x},
      "assignee_distribution": {"张三":x, ...},
      "type_distribution":    {"硬件故障":x, ...},       # 标题关键词归类
      "title_samples": [str, ...],                      # 最多 8 条样例（用于 LLM 推断高频问题）
      "status_by_day":      [{"date":"..", "已完成":x, "进行中":x, "未完成":x}, ...],  # 日维度趋势
      "completion_rate": float  # 已完成 / 总数
    }
    """
    conn = get_connection()
    cursor = conn.cursor()
    where = " WHERE create_time >= ? AND create_time <= ?"
    params = [start_date, end_date + " 23:59:59"]

    # 1) 总数
    cursor.execute(f"SELECT COUNT(*) FROM tickets{where}", params)
    total = cursor.fetchone()[0] or 0

    # 2) 状态分布
    cursor.execute(f"SELECT status, COUNT(*) FROM tickets{where} GROUP BY status", params)
    status_dist = {r[0]: r[1] for r in cursor.fetchall()}

    # 3) 优先级分布（用 priority 列，没有则统一回 0）
    priority_dist = {"高": 0, "中": 0, "低": 0}
    try:
        cursor.execute(f"SELECT priority, COUNT(*) FROM tickets{where} GROUP BY priority", params)
        for r in cursor.fetchall():
            key = str(r[0])
            if key in priority_dist:
                priority_dist[key] = r[1]
            else:
                priority_dist[key] = r[1]
    except Exception:
        pass

    # 4) 负责人分布
    cursor.execute(f"SELECT assignee, COUNT(*) FROM tickets{where} GROUP BY assignee", params)
    assignee_dist = {r[0]: r[1] for r in cursor.fetchall()}

    # 5) 类型分布（按 title 关键词粗略归类，便于发现高频问题）
    cursor.execute(f"SELECT title FROM tickets{where}", params)
    titles = [r[0] for r in cursor.fetchall()]
    type_keywords = {
        "网络类":    ["网络", "断网", "丢包", "延迟", "无法访问", "VPN"],
        "服务器硬件": ["服务器", "磁盘", "硬盘", "内存", "CPU", "电源", "宕机", "重启"],
        "应用系统":  ["应用", "系统", "软件", "登录", "报错", "无法打开", "崩溃"],
        "安全合规":  ["安全", "病毒", "漏洞", "补丁", "权限", "合规", "审计"],
        "办公终端":  ["电脑", "笔记本", "打印机", "投影", "邮箱", "OA"],
    }
    type_dist: dict[str, int] = {k: 0 for k in type_keywords}
    for t in titles:
        t_low = (t or "").lower()
        matched = False
        for cat, kws in type_keywords.items():
            if any(kw.lower() in t_low for kw in kws):
                type_dist[cat] += 1
                matched = True
                break
        if not matched:
            type_dist.setdefault("其他", 0)
            type_dist["其他"] += 1

    # 6) 日维度趋势（按天 group status）—— 用 SQL Server 兼容函数
    status_by_day: list[dict] = []
    try:
        cursor.execute(
            f"""
            SELECT CONVERT(varchar(10), create_time, 23) AS d, status, COUNT(*)
            FROM tickets{where}
            GROUP BY CONVERT(varchar(10), create_time, 23), status
            ORDER BY d
            """,
            params,
        )
        bucket: dict[str, dict] = {}
        for d, st, cnt in cursor.fetchall():
            bucket.setdefault(d, {"date": d, "未完成": 0, "进行中": 0, "已完成": 0})
            if st in bucket[d]:
                bucket[d][st] = cnt
        status_by_day = list(bucket.values())
    except Exception as e:
        # 兜底：DB 函数不可用时不阻塞整体报告
        print(f"[db_service] status_by_day 失败: {e}")
        status_by_day = []

    # 7) 完成率
    done = status_dist.get("已完成", 0)
    completion_rate = round(done / total, 4) if total > 0 else 0.0

    # 8) 计算天数
    try:
        d0 = datetime.strptime(start_date, "%Y-%m-%d")
        d1 = datetime.strptime(end_date, "%Y-%m-%d")
        days = (d1 - d0).days
    except Exception:
        days = 0

    return {
        "filter": {"start_date": start_date, "end_date": end_date, "days": days},
        "total": total,
        "status_distribution": status_dist,
        "priority_distribution": priority_dist,
        "assignee_distribution": assignee_dist,
        "type_distribution": type_dist,
        "title_samples": titles[:8],
        "status_by_day": status_by_day,
        "completion_rate": completion_rate,
    }


def get_tickets_paginated(page: int = 1, limit: int = 10) -> list:
    """分页查询工单列表（含明细宽表字段）"""
    conn = get_connection()
    cursor = conn.cursor()
    offset = (page - 1) * limit
    cursor.execute(
        "SELECT id, title, status, priority, assignee, create_time, updated_at "
        "FROM tickets ORDER BY create_time DESC "
        "OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",
        offset, limit
    )
    return [
        {
            "id": _fmt_tid(r[0]),
            "title": r[1],
            "status": r[2],
            "priority": r[3],
            "assignee": r[4],
            "create_time": _fmt_time(r[5]),
        }
        for r in cursor.fetchall()
    ]


# ========== 工单状态机：强制流转规则 ==========

_STATUS_FLOW = {
    "未完成": ["进行中"],           # 未完成 → 只能改为进行中
    "进行中": ["已完成"],           # 进行中 → 只能改为已完成
    "已完成": [],                   # 已完成 → 不允许再改
}


def update_ticket_status(tid, new_status: str) -> bool:
    """
    修改工单状态（带状态机校验）
    规则：未完成 → 进行中 → 已完成，禁止跳跃和回退
    返回 True 表示成功；若违规，抛出 ValueError
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 1. 查当前状态
    tid = str(tid).strip() if tid is not None else ""
    cursor.execute("SELECT status, title FROM tickets WHERE id = ?", tid)
    row = cursor.fetchone()
    if not row:
        return False
    current_status = row[0]
    ticket_title = row[1]

    # 2. 相同状态跳过
    if current_status == new_status:
        print(f"[DB] 工单 {tid} 已是「{new_status}」，无需修改")
        return True

    # 3. 校验流转规则
    allowed = _STATUS_FLOW.get(current_status, [])
    if new_status not in allowed:
        hint = ""
        if current_status == "未完成" and new_status == "已完成":
            hint = f"工单当前处于「未完成」状态，不能直接跳到「已完成」，请先将其改为「进行中」。"
        elif current_status == "已完成":
            hint = f"工单「{ticket_title}」已完成，不能回退状态。"
        else:
            hint = f"工单「{ticket_title}」当前「{current_status}」，不能改为「{new_status}」。"
        raise ValueError(hint)

    # 4. 合法则更新
    cursor.execute(
        "UPDATE tickets SET status = ? WHERE id = ?",
        new_status, tid
    )
    print(f"[DB] ✅ 工单 {tid}: 「{current_status}」→「{new_status}」")
    return cursor.rowcount > 0


# ========== 新建工单 ==========

def create_ticket(title: str, priority: str, assignee: str, status: str = "未完成", description: str = "") -> dict:
    """创建新工单"""
    if not title or not title.strip():
        return {"ok": False, "reason": "工单标题不能为空"}
    if priority not in ("高", "中", "低"):
        return {"ok": False, "reason": "优先级必须为 高/中/低"}
    if not assignee or not assignee.strip():
        return {"ok": False, "reason": "负责人不能为空"}
    if status not in ("未完成", "进行中", "已完成"):
        return {"ok": False, "reason": "状态无效"}

    conn = get_connection()
    cursor = conn.cursor()

    # 自动生成 ID: TKT-YYYYMMDD-XXXX（每日序号重置）
    today = datetime.utcnow().strftime("%Y%m%d")
    prefix = f"TKT-{today}-"
    cursor.execute("SELECT MAX(id) FROM tickets WHERE id LIKE ?", (prefix + '%',))
    max_id = cursor.fetchone()[0]
    if max_id:
        seq = int(max_id.split('-')[-1]) + 1
    else:
        seq = 1
    new_id = f"{prefix}{seq:04d}"

    now = datetime.utcnow()
    cursor.execute(
        "INSERT INTO tickets (id, title, status, priority, create_time, assignee, description, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        new_id, title.strip(), status, priority, now, assignee.strip(), description.strip() if description else "", now
    )
    print(f"[DB] ✅ 新建工单 {new_id}: {title.strip()}")

    return {
        "ok": True,
        "ticket": {
            "id": new_id, "title": title.strip(),
            "status": status, "priority": priority,
            "assignee": assignee.strip(), "create_time": _fmt_time(now),
            "description": description.strip() if description else ""
        }
    }


# ========== 更新工单（状态+优先级） ==========

def update_ticket(ticket_id, status: str = None, priority: str = None, description: str = None, operator: str = '系统') -> dict:
    """
    更新工单状态、优先级和/或内容描述
    - status: 可选，按状态机规则校验
    - priority: 可选，直接覆盖
    - description: 可选，直接覆盖
    - operator: 操作人，默认'系统'
    当状态发生变化时自动记录工单历史
    """
    conn = get_connection()
    cursor = conn.cursor()
    ticket_id = str(ticket_id).strip() if ticket_id is not None else ""
    cursor.execute("SELECT id, title, status, priority, create_time, assignee, description, updated_at FROM tickets WHERE id = ?", ticket_id)
    row = cursor.fetchone()
    if not row:
        return {"ok": False, "reason": f"工单 {ticket_id} 不存在"}

    current_status = row[2]
    current_priority = row[3]
    current_description = row[6]
    changed = []

    # 更新状态
    if status and status != current_status:
        if status not in ("未完成", "进行中", "已完成"):
            return {"ok": False, "reason": "状态值无效"}
        allowed = _STATUS_FLOW.get(current_status, [])
        if status not in allowed:
            hint = f"工单当前「{current_status}」，不能直接改为「{status}」"
            if current_status == "未完成" and status == "已完成":
                hint = "工单处于「未完成」状态，不能直接跳到「已完成」，请先改为「进行中」"
            elif current_status == "已完成":
                hint = "工单已完成，不能回退状态"
            return {"ok": False, "reason": hint}
        cursor.execute("UPDATE tickets SET status = ?, updated_at = GETDATE() WHERE id = ?", status, ticket_id)
        changed.append(f"状态: {current_status} -> {status}")
        # 记录状态变更历史
        add_ticket_history(ticket_id, "状态变更", operator, current_status, status)

    # 更新优先级
    if priority and priority != current_priority:
        if priority not in ("高", "中", "低"):
            return {"ok": False, "reason": "优先级必须为 高/中/低"}
        cursor.execute("UPDATE tickets SET priority = ?, updated_at = GETDATE() WHERE id = ?", priority, ticket_id)
        changed.append(f"优先级: {current_priority} -> {priority}")

    # 更新内容描述
    if description is not None and description != current_description:
        cursor.execute("UPDATE tickets SET description = ?, updated_at = GETDATE() WHERE id = ?", description, ticket_id)
        changed.append(f"内容描述已更新")

    # 没有变化时仍返回正确结果
    if not changed:
        return {"ok": True, "message": "没有需要更新的字段"}

    # 重新获取更新后的工单
    cursor.execute("SELECT id, title, status, priority, create_time, assignee, description, updated_at FROM tickets WHERE id = ?", ticket_id)
    r = cursor.fetchone()
    updated_ticket = {
        "id": _fmt_tid(r[0]), "title": r[1], "status": r[2], "priority": r[3],
        "create_time": _fmt_time(r[4]) if r[4] else "", "assignee": r[5], "description": r[6]
    }
    return {"ok": True, "message": "; ".join(changed), "ticket": updated_ticket}


# ========== 工单历史记录 ==========

def add_ticket_history(ticket_id, action: str, operator: str, old_value: str = None, new_value: str = None, remark: str = None):
    """添加工单历史记录"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO ticket_history (ticket_id, action, operator, old_value, new_value, remark) VALUES (?, ?, ?, ?, ?, ?)",
        (ticket_id, action, operator, old_value, new_value, remark)
    )


def get_ticket_history(ticket_id) -> list:
    """获取工单历史记录，按时间倒序"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, ticket_id, action, operator, old_value, new_value, remark, created_at "
        "FROM ticket_history WHERE ticket_id = ? ORDER BY created_at DESC",
        ticket_id
    )
    return [
        {"id": r[0], "ticket_id": r[1], "action": r[2], "operator": r[3],
         "old_value": r[4], "new_value": r[5], "remark": r[6],
         "created_at": _fmt_time(r[7])}
        for r in cursor.fetchall()
    ]


# ========== 智能工单指派 ==========

def get_assign_candidates(ticket_id) -> list:
    """
    获取可指派候选人列表，含工作负载指标，按推荐分数排序
    排除 high_priority_count >= 3 的候选人
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT s.name, ISNULL(r.role_name, '未分配') AS role_name,
               (SELECT COUNT(*) FROM tickets t WHERE t.assignee = s.name AND t.priority = '高' AND t.status != '已完成') AS high_priority_count,
               (SELECT COUNT(*) FROM tickets t WHERE t.assignee = s.name AND t.status != '已完成') AS total_pending
        FROM staff s
        LEFT JOIN staff_roles r ON s.role_id = r.role_id
        WHERE s.status = '启用'
        ORDER BY s.name
    """)
    rows = cursor.fetchall()

    candidates = []
    for r in rows:
        name = r[0]
        role_name = r[1]
        high_priority_count = r[2] or 0
        total_pending = r[3] or 0

        # 排除高优先级工单过多的候选人
        if high_priority_count >= 3:
            continue

        # 计算推荐分数：总待办越少分数越高（满分100，每件待办扣10分）
        score = max(0, 100 - total_pending * 10)

        candidate = {
            "name": name,
            "role_name": role_name,
            "high_priority_count": high_priority_count,
            "total_pending": total_pending,
            "score": score,
            "warning": None,
        }
        # 如果总待办 >= 10，添加警告
        if total_pending >= 10:
            candidate["warning"] = f"{name} 当前有 {total_pending} 个待处理工单，负载较高"

        candidates.append(candidate)

    # 按推荐分数降序排列
    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates


def assign_ticket(ticket_id, new_assignee: str) -> dict:
    """
    指派工单给负责人
    检查工单存在且未完成，更新assignee后记录历史
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 1. 检查工单存在
    ticket_id = str(ticket_id).strip() if ticket_id is not None else ""
    cursor.execute("SELECT id, title, status, priority, create_time, assignee, description, updated_at FROM tickets WHERE id = ?", ticket_id)
    row = cursor.fetchone()
    if not row:
        return {"ok": False, "reason": f"工单 {ticket_id} 不存在"}

    current_assignee = row[5]
    current_status = row[2]

    # 2. 检查是否为已完成
    if current_status == "已完成":
        return {"ok": False, "reason": "已完成工单不能指派"}

    # 3. 更新负责人
    cursor.execute("UPDATE tickets SET assignee = ?, updated_at = GETDATE() WHERE id = ?", new_assignee, ticket_id)

    # 4. 记录历史
    add_ticket_history(ticket_id, "指派", "系统", current_assignee, new_assignee)

    # 5. 返回更新后的工单
    cursor.execute("SELECT id, title, status, priority, create_time, assignee, description, updated_at FROM tickets WHERE id = ?", ticket_id)
    r = cursor.fetchone()
    updated_ticket = {
        "id": _fmt_tid(r[0]), "title": r[1], "status": r[2], "priority": r[3],
        "create_time": _fmt_time(r[4]) if r[4] else "", "assignee": r[5], "description": r[6]
    }
    return {"ok": True, "message": f"工单已指派给 {new_assignee}", "ticket": updated_ticket}


def get_latest_metrics() -> dict:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT TOP 1 * FROM metrics_snapshots ORDER BY snapshot_time DESC")
        r = cursor.fetchone()
        if r:
            return {"cpu_usage_percent": r[1], "memory_usage_percent": r[2], "disk_usage_percent": r[3],
                    "network_in_mbps": r[4], "network_out_mbps": r[5], "disk_read_mbps": r[6], "disk_write_mbps": r[7],
                    "api_latency_ms": r[8] if len(r) > 8 else 120,
                    "error_rate_percent": r[9] if len(r) > 9 else 0.5,
                    "qps_or_tps": r[10] if len(r) > 10 else 850,
                    "gpu_usage_percent": r[11] if len(r) > 11 else 45,
                    "gpu_temp_celsius": r[12] if len(r) > 12 else 55,
                    "container_active_count": r[13] if len(r) > 13 else 12,
                    "tcp_established": r[14] if len(r) > 14 else 600,
                    "security_intercept_count": r[15] if len(r) > 15 else 0,
                    "health_score": r[16] if len(r) > 16 else 95}
    except Exception as e:
        print(f"[DB] get_latest_metrics 降级到 Mock: {e}")
    return dict(SERVERS_METRICS, **{
        "api_latency_ms": 120, "error_rate_percent": 0.5, "qps_or_tps": 850,
        "gpu_usage_percent": 45, "gpu_temp_celsius": 55, "container_active_count": 12,
        "tcp_established": 600, "security_intercept_count": 0, "health_score": 95
    })


def get_historical_metrics(limit: int = 20) -> list:
    """获取历史监控快照，DB 不可用时自动生成 Mock 数据"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT TOP (?)
                snapshot_time, cpu_usage_percent, memory_usage_percent,
                disk_usage_percent, network_in_mbps, network_out_mbps,
                disk_read_mbps, disk_write_mbps,
                api_latency_ms, error_rate_percent, qps_or_tps,
                gpu_usage_percent, gpu_temp_celsius, container_active_count,
                tcp_established, security_intercept_count, health_score
            FROM metrics_snapshots
            ORDER BY snapshot_time DESC
        """, (limit,))
        rows = cursor.fetchall()
        if rows:
            rows.reverse()
            return [{
                "timestamp": r[0].isoformat(),
                "cpu_usage_percent": r[1], "memory_usage_percent": r[2],
                "disk_usage_percent": r[3], "network_in_mbps": r[4],
                "network_out_mbps": r[5], "disk_read_mbps": r[6], "disk_write_mbps": r[7],
                "api_latency_ms": r[8] if len(r) > 8 else 120,
                "error_rate_percent": r[9] if len(r) > 9 else 0.5,
                "qps_or_tps": r[10] if len(r) > 10 else 850,
                "gpu_usage_percent": r[11] if len(r) > 11 else 45,
                "gpu_temp_celsius": r[12] if len(r) > 12 else 55,
                "container_active_count": r[13] if len(r) > 13 else 12,
                "tcp_established": r[14] if len(r) > 14 else 600,
                "security_intercept_count": r[15] if len(r) > 15 else 0,
                "health_score": r[16] if len(r) > 16 else 95
            } for r in rows]
    except Exception as e:
        print(f"[DB] get_historical_metrics 降级到 Mock: {e}")

    # Mock 降级：生成 limit 条随机历史数据
    base = SERVERS_METRICS
    now = datetime.utcnow()
    result = []
    cpu, mem = base["cpu_usage_percent"], base["memory_usage_percent"]
    latency, qps = 120.0, 850.0
    for i in range(limit):
        t = now - timedelta(minutes=limit - 1 - i)
        cpu = max(0, min(100, cpu + random.uniform(-3, 3)))
        mem = max(0, min(100, mem + random.uniform(-2, 2)))
        latency = max(30, min(500, latency + random.uniform(-15, 15)))
        qps = max(100, min(2500, qps + random.uniform(-80, 80)))
        result.append({
            "timestamp": t.isoformat(),
            "cpu_usage_percent": round(cpu, 1),
            "memory_usage_percent": round(mem, 1),
            "disk_usage_percent": base["disk_usage_percent"],
            "network_in_mbps": round(base["network_in_mbps"] + random.uniform(-10, 10), 1),
            "network_out_mbps": round(base["network_out_mbps"] + random.uniform(-8, 8), 1),
            "disk_read_mbps": round(base["disk_read_mbps"] + random.uniform(-5, 5), 1),
            "disk_write_mbps": round(base["disk_write_mbps"] + random.uniform(-4, 4), 1),
            "api_latency_ms": round(latency, 1),
            "error_rate_percent": round(0.3 + random.uniform(0, 0.5), 2),
            "qps_or_tps": round(qps, 0),
            "gpu_usage_percent": round(45 + random.uniform(-10, 10), 1),
            "gpu_temp_celsius": round(55 + random.uniform(-5, 5), 1),
            "container_active_count": random.randint(10, 15),
            "tcp_established": random.randint(400, 900),
            "security_intercept_count": random.randint(0, 3),
            "health_score": round(92 + random.uniform(0, 8), 1),
        })
    return result


# ========== 系统配置相关 ==========

_SYS_CONFIG_DEFAULTS = {
    # SLA 告警管理
    "sla_timeout_hours": "4",
    "sla_warning_pct": "75",
    # 工单新建规则
    "ticket_desc_required": "0",
    "ticket_default_priority": "中",
    "ticket_desc_max_chars": "500",
    # 看板自动刷新
    "dashboard_refresh_sec": "0",
    # 卡片五：通知与消息推送
    "notify_new_ticket": "1",
    "notify_status_change": "1",
    "notify_overdue_method": "all",
    "notify_quiet_start": "22:00",
    "notify_quiet_end": "08:00",
    # 卡片七：权限与操作门槛
    "confirm_delete": "1",
    "confirm_assign": "1",
    "confirm_schedule": "1",
    "batch_ops_limit": "50",
    # 卡片九：数据导出配置
    "export_format": "xlsx",
    "export_default_fields": "id,title,status,priority,assignee,create_time",
    "export_time_range_months": "3",
    "export_max_rows": "10000",
}


def seed_config_defaults():
    """初始化 sys_config 默认值（幂等：已存在的键不覆盖）"""
    conn = get_connection()
    cursor = conn.cursor()
    for key, val in _SYS_CONFIG_DEFAULTS.items():
        try:
            cursor.execute(
                "IF NOT EXISTS (SELECT 1 FROM sys_config WHERE config_key = ?) "
                "INSERT INTO sys_config (config_key, config_value) VALUES (?, ?)",
                (key, key, val)
            )
        except Exception as e:
            print(f"[DB] ⚠️ 写入默认配置 {key} 失败: {e}")
    print(f"[DB] ✅ sys_config 默认值已初始化")


def get_config() -> dict:
    """读取所有系统配置"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT config_key, config_value FROM sys_config")
    return {r[0]: r[1] for r in cursor.fetchall()}


def get_config_value(key: str, default: str = "") -> str:
    """读取单个配置值"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT config_value FROM sys_config WHERE config_key = ?", key)
    row = cursor.fetchone()
    return row[0] if row else default


def save_config(config: dict) -> dict:
    """保存配置（MERGE 语义：存在则更新，不存在则插入）"""
    conn = get_connection()
    cursor = conn.cursor()
    updated = []
    for key, val in config.items():
        if key not in _SYS_CONFIG_DEFAULTS:
            continue  # 忽略非法 key
        try:
            cursor.execute(
                "MERGE sys_config AS t "
                "USING (SELECT ? AS config_key, ? AS config_value) AS s "
                "ON t.config_key = s.config_key "
                "WHEN MATCHED THEN UPDATE SET config_value = s.config_value, updated_at = GETDATE() "
                "WHEN NOT MATCHED THEN INSERT (config_key, config_value) VALUES (s.config_key, s.config_value);",
                (key, str(val))
            )
            updated.append(key)
        except Exception as e:
            print(f"[DB] ⚠️ 保存配置 {key}={val} 失败: {e}")
    return {"updated": updated}


# ========== 人员管理相关 ==========

# 人员角色种子数据
_STAFF_ROLES_SEED = ROLES  # 从 seed_data_v2 导入

# 人员种子数据
_STAFF_SEED = STAFF  # 从 seed_data_v2 导入


def seed_staff_roles():
    """初始化 staff_roles 角色数据（幂等）"""
    conn = get_connection()
    cursor = conn.cursor()
    for name in _STAFF_ROLES_SEED:
        try:
            cursor.execute(
                "IF NOT EXISTS (SELECT 1 FROM staff_roles WHERE role_name = ?) "
                "INSERT INTO staff_roles (role_name) VALUES (?)",
                (name, name)
            )
        except Exception as e:
            print(f"[DB] ⚠️ 写入角色 {name} 失败: {e}")
    print(f"[DB] ✅ staff_roles 默认数据已初始化 ({len(_STAFF_ROLES_SEED)} 个角色)")


def seed_staff():
    """初始化 staff 人员数据（覆盖旧数据，确保与 seed_data_v2 一致）"""
    conn = get_connection()
    cursor = conn.cursor()

    # 清空旧数据后重新导入
    cursor.execute("DELETE FROM staff")

    # 先建角色 name→id 映射
    cursor.execute("SELECT role_id, role_name FROM staff_roles")
    role_map = {r[1]: r[0] for r in cursor.fetchall()}

    for s in _STAFF_SEED:
        rid = role_map.get(s["role_name"])
        try:
            cursor.execute(
                "INSERT INTO staff (staff_no, name, role_id, phone, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (s["staff_no"], s["name"], rid, s["phone"], s["status"],
                 datetime.fromisoformat(s["hire_date"]) if s.get("hire_date") else datetime.utcnow())
            )
        except Exception as e:
            print(f"[DB] ⚠️ 写入人员 {s['name']} 失败: {e}")
    print(f"[DB] ✅ staff 数据已导入 ({len(_STAFF_SEED)} 人)")


def seed_schedule():
    """初始化全年排班数据（覆盖旧数据），8个月历史 + 4个月未来"""
    from datetime import date as _date, timedelta as _td
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM staff_schedule")

    today = _date.today()
    # 从 8 个月前到今天 + 未来 4 个月，覆盖约一年范围
    START = today.replace(day=1) - _td(days=240)  # 约 8 个月前
    END = today + _td(days=120)  # 未来 4 个月
    schedules = generate_schedule(START, END)

    sql = "INSERT INTO staff_schedule (staff_name, shift_date, shift_type) VALUES (?, ?, ?)"
    count = 0
    for s in schedules:
        try:
            cursor.execute(sql, (s["staff_name"], s["shift_date"], s["shift_type"]))
            count += 1
        except Exception as e:
            print(f"[DB] ⚠️ 排班 {s['staff_name']}/{s['shift_date']} 失败: {e}")
    conn.commit()
    print(f"[DB] ✅ staff_schedule 已导入 ({count}/{len(schedules)} 条，{START} ~ {END})")


# ---------- 人员档案 CRUD ----------

def get_staff_list(keyword: str = None) -> list:
    """
    获取人员列表（含待处理工单数统计）
    返回每个人员的：id, staff_no, name, role_name, phone, pending_tickets, status
    """
    conn = get_connection()
    cursor = conn.cursor()
    if keyword:
        kw = f"%{keyword.strip()}%"
        cursor.execute("""
            SELECT s.id, s.staff_no, s.name, ISNULL(r.role_name, '未分配') AS role_name,
                   s.phone, s.status,
                   (SELECT COUNT(*) FROM tickets t WHERE t.assignee = s.name AND t.status != '已完成') AS pending_tickets
            FROM staff s
            LEFT JOIN staff_roles r ON s.role_id = r.role_id
            WHERE s.name LIKE ? OR s.phone LIKE ? OR s.staff_no LIKE ?
            ORDER BY s.id
        """, (kw, kw, kw))
    else:
        cursor.execute("""
            SELECT s.id, s.staff_no, s.name, ISNULL(r.role_name, '未分配') AS role_name,
                   s.phone, s.status,
                   (SELECT COUNT(*) FROM tickets t WHERE t.assignee = s.name AND t.status != '已完成') AS pending_tickets
            FROM staff s
            LEFT JOIN staff_roles r ON s.role_id = r.role_id
            ORDER BY s.id
        """)
    rows = cursor.fetchall()
    result = []
    for r in rows:
        staff_id = r[0]
        # 查询该员工关联的标签
        cursor.execute("""
            SELECT t.tag_id, t.tag_name, t.tag_color
            FROM staff_tags st JOIN role_tags t ON st.tag_id = t.tag_id
            WHERE st.staff_id = ? ORDER BY t.tag_id
        """, staff_id)
        tags = [{"tag_id": x[0], "tag_name": x[1], "tag_color": x[2]} for x in cursor.fetchall()]
        result.append({
            "id": staff_id, "staff_no": r[1], "name": r[2], "role_name": r[3],
            "phone": r[4], "status": r[5], "pending_tickets": r[6], "tags": tags,
        })
    return result


def create_staff(data: dict) -> dict:
    """新增人员"""
    conn = get_connection()
    cursor = conn.cursor()
    name = data.get("name", "").strip()
    phone = data.get("phone", "").strip()
    role_name = data.get("role_name", "").strip()

    if not name or not phone:
        return {"ok": False, "reason": "姓名和手机号不能为空"}

    # 生成工号
    cursor.execute("SELECT MAX(id) FROM staff")
    max_id = cursor.fetchone()[0] or 0
    staff_no = f"OP{max_id + 1:03d}"

    # 查找 role_id
    role_id = None
    if role_name:
        cursor.execute("SELECT role_id FROM staff_roles WHERE role_name = ?", role_name)
        row = cursor.fetchone()
        if row:
            role_id = row[0]

    cursor.execute(
        "INSERT INTO staff (staff_no, name, role_id, phone) VALUES (?, ?, ?, ?)",
        (staff_no, name, role_id, phone)
    )
    return {"ok": True, "staff_no": staff_no}


def update_staff(staff_id: int, data: dict) -> dict:
    """编辑人员信息"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM staff WHERE id = ?", staff_id)
    if not cursor.fetchone():
        return {"ok": False, "reason": "人员不存在"}

    name = data.get("name", "").strip()
    phone = data.get("phone", "").strip()
    role_name = data.get("role_name", "").strip()
    new_status = data.get("status", "").strip()

    if new_status == "停用":
        # 安全校验：名下有待处理工单时禁止停用
        cursor.execute(
            "SELECT COUNT(*) FROM tickets WHERE assignee = (SELECT name FROM staff WHERE id = ?) AND status != '已完成'",
            staff_id
        )
        pending = cursor.fetchone()[0]
        if pending > 0:
            return {"ok": False, "reason": f"无法停用！该人员名下尚有 {pending} 个未完成的工单，请先转派给他人后再执行！"}

    # 更新
    sets = []
    params = []
    if name:
        sets.append("name = ?")
        params.append(name)
    if phone:
        sets.append("phone = ?")
        params.append(phone)
    if role_name:
        cursor.execute("SELECT role_id FROM staff_roles WHERE role_name = ?", role_name)
        row = cursor.fetchone()
        if row:
            sets.append("role_id = ?")
            params.append(row[0])
    if new_status:
        sets.append("status = ?")
        params.append(new_status)

    if sets:
        params.append(staff_id)
        cursor.execute(f"UPDATE staff SET {', '.join(sets)} WHERE id = ?", params)

    return {"ok": True}


def reset_staff_password(staff_id: int, new_password: str = "123456") -> dict:
    """重置人员密码（MD5），默认 123456"""
    if not new_password or len(new_password) < 6 or len(new_password) > 32:
        return {"ok": False, "reason": "密码长度需在 6-32 位之间"}
    pwd_hash = hashlib.md5(new_password.encode("utf-8")).hexdigest()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM staff WHERE id = ?", staff_id)
    if not cursor.fetchone():
        return {"ok": False, "reason": "人员不存在"}
    cursor.execute(
        "UPDATE staff SET password_hash = ? WHERE id = ?",
        pwd_hash, staff_id
    )
    return {"ok": True}


def get_staff_detail(staff_id: int) -> dict:
    """获取人员详情（含全部待处理工单）"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.id, s.staff_no, s.name, ISNULL(r.role_name, '未分配'), s.phone, s.status, s.created_at
        FROM staff s LEFT JOIN staff_roles r ON s.role_id = r.role_id
        WHERE s.id = ?
    """, staff_id)
    row = cursor.fetchone()
    if not row:
        return None

    cursor.execute(
        "SELECT id, title, status FROM tickets WHERE assignee = ? AND status != '已完成' ORDER BY create_time DESC",
        row[2]
    )
    tickets = [{"id": _fmt_tid(r[0]), "title": r[1], "status": r[2]} for r in cursor.fetchall()]

    # 查询该员工关联的标签
    cursor.execute("""
        SELECT t.tag_id, t.tag_name, t.tag_color
        FROM staff_tags st JOIN role_tags t ON st.tag_id = t.tag_id
        WHERE st.staff_id = ? ORDER BY t.tag_id
    """, staff_id)
    tags = [{"tag_id": x[0], "tag_name": x[1], "tag_color": x[2]} for x in cursor.fetchall()]

    return {
        "id": row[0], "staff_no": row[1], "name": row[2], "role_name": row[3],
        "phone": row[4], "status": row[5], "created_at": row[6].isoformat() if row[6] else "",
        "recent_tickets": tickets, "tags": tags,
    }


# ---------- 排班管理 ----------

def get_schedule(year: int = None, month: int = None) -> dict:
    """获取排班数据与统计指标（按月查询）"""
    from datetime import date as _date, timedelta as _td
    from calendar import monthrange
    conn = get_connection()
    cursor = conn.cursor()

    today = _date.today()
    if year is None or month is None:
        year, month = today.year, today.month

    # 本月第一天 / 最后一天
    first_day = _date(year, month, 1)
    if month == 12:
        next_first = _date(year + 1, 1, 1)
    else:
        next_first = _date(year, month + 1, 1)
    last_day = next_first - _td(days=1)
    days_in_month = monthrange(year, month)[1]

    # KPI: 今日值班人数
    today_str = today.isoformat()
    cursor.execute(
        "SELECT COUNT(DISTINCT staff_name) FROM staff_schedule WHERE shift_date = ? AND shift_type != '休息'",
        today_str
    )
    today_on_duty = cursor.fetchone()[0] or 0

    # KPI: 当前在线（启用的人员数）
    cursor.execute("SELECT COUNT(*) FROM staff WHERE status = '启用'")
    online_count = cursor.fetchone()[0] or 0

    # KPI: 本月累计排班次数
    cursor.execute(
        "SELECT COUNT(*) FROM staff_schedule WHERE shift_date >= ? AND shift_date < ? AND shift_type != '休息'",
        (first_day.isoformat(), next_first.isoformat())
    )
    month_total = cursor.fetchone()[0] or 0

    # 本月所有排班记录
    cursor.execute(
        "SELECT staff_name, shift_date, shift_type FROM staff_schedule "
        "WHERE shift_date >= ? AND shift_date < ? ORDER BY shift_date, staff_name",
        (first_day.isoformat(), next_first.isoformat())
    )
    schedule_rows = [
        {"staff_name": r[0], "shift_date": str(r[1]), "shift_type": r[2]}
        for r in cursor.fetchall()
    ]

    # 全部启用人员（用于日历显示"未排班"）
    cursor.execute("SELECT name FROM staff WHERE status = '启用' ORDER BY name")
    all_staff = [r[0] for r in cursor.fetchall()]

    # 本月每人排班负荷
    from collections import Counter
    load_counter = Counter()
    for s in schedule_rows:
        if s["shift_type"] != "休息":
            load_counter[s["staff_name"]] += 1
    load_data = [
        {"staff_name": name, "duty_days": cnt}
        for name, cnt in sorted(load_counter.items(), key=lambda x: -x[1])
    ]

    return {
        "kpi": {
            "today_on_duty": today_on_duty,
            "online_count": online_count,
            "month_total_shifts": month_total,
        },
        "schedule": schedule_rows,
        "load_data": load_data,
        "all_staff": all_staff,
        "year": year,
        "month": month,
        "days_in_month": days_in_month,
        "first_weekday": first_day.weekday(),  # 周一=0 ... 周日=6
    }


def get_schedule_by_date(date_str: str, shift_type: str = None) -> dict:
    """
    查询指定日期的排班详情（供意图识别使用）
    Args:
        date_str: 日期字符串 "YYYY-MM-DD"
        shift_type: 可选，过滤班次类型（早班/下午班/晚班）
    Returns:
        {"date": "YYYY-MM-DD", "shifts": [...], "total_on_duty": N}
    """
    conn = get_connection()
    cursor = conn.cursor()

    if shift_type and shift_type in ("早班", "下午班", "晚班", "休息"):
        cursor.execute(
            "SELECT staff_name, shift_type FROM staff_schedule WHERE shift_date = ? AND shift_type = ? ORDER BY shift_type, staff_name",
            (date_str, shift_type)
        )
    else:
        cursor.execute(
            "SELECT staff_name, shift_type FROM staff_schedule WHERE shift_date = ? ORDER BY shift_type, staff_name",
            date_str
        )

    rows = cursor.fetchall()
    shifts = [{"staff_name": r[0], "shift_type": r[1]} for r in rows]

    # 当日值班人数（不含休息）
    cursor.execute(
        "SELECT COUNT(DISTINCT staff_name) FROM staff_schedule WHERE shift_date = ? AND shift_type != '休息'",
        date_str
    )
    total_on_duty = cursor.fetchone()[0] or 0

    # 按班次分组
    grouped = {}
    for s in shifts:
        st = s["shift_type"]
        if st not in grouped:
            grouped[st] = []
        grouped[st].append(s["staff_name"])

    return {
        "date": date_str,
        "shifts": shifts,
        "grouped": grouped,
        "total_on_duty": total_on_duty,
        "shift_type_filter": shift_type,
    }


def get_schedule_today() -> dict:
    """查询今日值班情况"""
    from datetime import date as _date
    today = _date.today().isoformat()
    result = get_schedule_by_date(today)
    result["kpi"] = {
        "today_on_duty": result["total_on_duty"],
    }
    return result


def get_schedule_online() -> dict:
    """查询当前在线人员数"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM staff WHERE status = '启用'")
    online_count = cursor.fetchone()[0] or 0

    cursor.execute("SELECT name FROM staff WHERE status = '启用' ORDER BY name")
    online_staff = [r[0] for r in cursor.fetchall()]

    return {
        "online_count": online_count,
        "online_staff": online_staff,
    }


def get_schedule_month_stats() -> dict:
    """查询本月排班统计"""
    from datetime import date as _date, timedelta as _td
    today = _date.today()
    first_day = today.replace(day=1)
    if today.month == 12:
        next_first = _date(today.year + 1, 1, 1)
    else:
        next_first = _date(today.year, today.month + 1, 1)

    conn = get_connection()
    cursor = conn.cursor()

    # 本月累计排班次数（不含休息）
    cursor.execute(
        "SELECT COUNT(*) FROM staff_schedule WHERE shift_date >= ? AND shift_date < ? AND shift_type != '休息'",
        (first_day.isoformat(), next_first.isoformat())
    )
    month_total = cursor.fetchone()[0] or 0

    # 今日值班人数
    today_str = today.isoformat()
    cursor.execute(
        "SELECT COUNT(DISTINCT staff_name) FROM staff_schedule WHERE shift_date = ? AND shift_type != '休息'",
        today_str
    )
    today_on_duty = cursor.fetchone()[0] or 0

    # 每人排班次数统计
    cursor.execute(
        "SELECT staff_name, COUNT(*) as cnt FROM staff_schedule "
        "WHERE shift_date >= ? AND shift_date < ? AND shift_type != '休息' "
        "GROUP BY staff_name ORDER BY cnt DESC",
        (first_day.isoformat(), next_first.isoformat())
    )
    load_data = [{"staff_name": r[0], "duty_days": r[1]} for r in cursor.fetchall()]

    return {
        "kpi": {
            "today_on_duty": today_on_duty,
            "month_total_shifts": month_total,
        },
        "load_data": load_data,
        "year": today.year,
        "month": today.month,
    }


def assign_schedule(staff_name: str, shift_date: str, shift_type: str) -> dict:
    """
    排班操作（供意图识别使用，封装 create_schedule）
    返回: {"ok": True/False, "reason": "..."}
    """
    return create_schedule({
        "staff_name": staff_name,
        "shift_date": shift_date,
        "shift_type": shift_type,
    })


def create_schedule(data: dict) -> dict:
    """生成/修改排班记录"""
    staff_name = data.get("staff_name", "").strip()
    shift_date = data.get("shift_date", "").strip()
    shift_type = data.get("shift_type", "").strip()

    if not staff_name or not shift_date or not shift_type:
        return {"ok": False, "reason": "参数不完整"}

    conn = get_connection()
    cursor = conn.cursor()

    try:
        # 先检查是否已存在
        cursor.execute(
            "SELECT COUNT(*) FROM staff_schedule WHERE staff_name = ? AND shift_date = ?",
            (staff_name, shift_date)
        )
        exists = cursor.fetchone()[0] > 0

        if exists:
            cursor.execute(
                "UPDATE staff_schedule SET shift_type = ? WHERE staff_name = ? AND shift_date = ?",
                (shift_type, staff_name, shift_date)
            )
        else:
            cursor.execute(
                "INSERT INTO staff_schedule (staff_name, shift_date, shift_type) VALUES (?, ?, ?)",
                (staff_name, shift_date, shift_type)
            )

        conn.commit()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


def delete_schedule(data: dict) -> dict:
    """删除排班记录"""
    staff_name = (data.get("staff_name") or "").strip()
    shift_date = (data.get("shift_date") or "").strip()
    if not staff_name or not shift_date:
        return {"ok": False, "reason": "参数不完整"}
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM staff_schedule WHERE staff_name = ? AND shift_date = ?",
            (staff_name, shift_date)
        )
        return {"ok": True, "deleted": cursor.rowcount}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


def batch_create_schedule(data: dict) -> dict:
    """
    批量排班：
    - staff_names: 人员列表
    - weekdays: 周几列表（0=周一 ... 6=周日）
    - shift_type: 班次
    - start_date / end_date: 起止日期（YYYY-MM-DD）
    对每位人员，在 [start_date, end_date] 区间内每个匹配的 weekday 生成一条排班
    """
    from datetime import date as _date, timedelta as _td
    staff_names = data.get("staff_names") or []
    weekdays = data.get("weekdays") or []
    shift_type = (data.get("shift_type") or "").strip()
    start_date = (data.get("start_date") or "").strip()
    end_date = (data.get("end_date") or "").strip()

    if not staff_names or not weekdays or not shift_type or not start_date or not end_date:
        return {"ok": False, "reason": "参数不完整"}
    if shift_type not in ("早班", "晚班", "休息"):
        return {"ok": False, "reason": "班次类型无效"}
    if start_date > end_date:
        return {"ok": False, "reason": "开始日期不能晚于结束日期"}

    try:
        sd = _date.fromisoformat(start_date)
        ed = _date.fromisoformat(end_date)
    except ValueError:
        return {"ok": False, "reason": "日期格式错误"}

    weekdays_set = set(int(w) for w in weekdays)

    conn = get_connection()
    cursor = conn.cursor()
    count = 0
    try:
        cur_date = sd
        while cur_date <= ed:
            # cur_date.weekday(): 周一=0 ... 周日=6
            if cur_date.weekday() in weekdays_set:
                for name in staff_names:
                    cursor.execute(
                        "MERGE staff_schedule AS t "
                        "USING (SELECT ? AS staff_name, ? AS shift_date, ? AS shift_type) AS s "
                        "ON t.staff_name = s.staff_name AND t.shift_date = s.shift_date "
                        "WHEN MATCHED THEN UPDATE SET shift_type = s.shift_type "
                        "WHEN NOT MATCHED THEN INSERT (staff_name, shift_date, shift_type) VALUES (s.staff_name, s.shift_date, s.shift_type);",
                        (name, cur_date.isoformat(), name, cur_date.isoformat(), shift_type)
                    )
                    count += 1
            cur_date += _td(days=1)
        return {"ok": True, "count": count}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


# ---------- 角色配置 ----------

def get_staff_roles() -> list:
    """获取所有角色列表（含关联人数和标签，一个角色可关联多个标签）"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.role_id, r.role_name, r.created_at, r.tag_id,
               t.tag_name, t.tag_color,
               (SELECT COUNT(*) FROM staff WHERE role_id = r.role_id) AS staff_count
        FROM staff_roles r
        LEFT JOIN role_tags t ON r.tag_id = t.tag_id
        ORDER BY r.role_id
    """)
    rows = cursor.fetchall()
    result = []
    for r in rows:
        role_id = r[0]
        # 收集该角色的全部标签（主标签 tag_id + 关联表 role_tag_rel）
        cursor.execute("""
            SELECT t.tag_id, t.tag_name, t.tag_color
            FROM role_tag_rel rel JOIN role_tags t ON rel.tag_id = t.tag_id
            WHERE rel.role_id = ? ORDER BY t.tag_id
        """, role_id)
        extra_tags = [{"tag_id": x[0], "tag_name": x[1], "tag_color": x[2]} for x in cursor.fetchall()]
        tags = extra_tags[:]
        # 主标签去重加入（避免与关联表重复）
        if r[3] and not any(t["tag_id"] == r[3] for t in tags):
            tags.insert(0, {"tag_id": r[3], "tag_name": r[4], "tag_color": r[5]})
        result.append({
            "role_id": role_id, "role_name": r[1],
            "created_at": r[2].isoformat() if r[2] else "",
            "tag_id": r[3],
            "tag_name": r[4],
            "tag_color": r[5],
            "tags": tags,
            "staff_count": r[6],
        })
    return result


def create_staff_role(role_name: str) -> dict:
    """新增角色"""
    name = role_name.strip()
    if not name:
        return {"ok": False, "reason": "角色名不能为空"}
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "IF NOT EXISTS (SELECT 1 FROM staff_roles WHERE role_name = ?) INSERT INTO staff_roles (role_name) VALUES (?)",
        (name, name)
    )
    return {"ok": True}


def update_staff_role(role_id: int, role_name: str) -> dict:
    """编辑角色名称"""
    name = role_name.strip()
    if not name:
        return {"ok": False, "reason": "角色名不能为空"}
    conn = get_connection()
    cursor = conn.cursor()
    # 检查重名
    cursor.execute("SELECT 1 FROM staff_roles WHERE role_name = ? AND role_id != ?", (name, role_id))
    if cursor.fetchone():
        return {"ok": False, "reason": f"角色名「{name}」已存在"}
    cursor.execute("UPDATE staff_roles SET role_name = ? WHERE role_id = ?", (name, role_id))
    return {"ok": True}


def delete_staff_role(role_id: int) -> dict:
    """删除角色（有关联人员则拒绝）"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM staff WHERE role_id = ?", role_id)
    if cursor.fetchone()[0] > 0:
        return {"ok": False, "reason": "该角色下有关联人员，无法删除"}
    cursor.execute("DELETE FROM role_tag_rel WHERE role_id = ?", role_id)
    cursor.execute("DELETE FROM staff_roles WHERE role_id = ?", role_id)
    return {"ok": True}


# ========== 角色标签管理 ==========

def get_role_tags() -> list:
    """获取所有角色标签"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT tag_id, tag_name, tag_color FROM role_tags ORDER BY tag_id")
    return [
        {"tag_id": r[0], "tag_name": r[1], "tag_color": r[2]}
        for r in cursor.fetchall()
    ]


def create_role_tag(tag_name: str, tag_color: str = "#3b82f6") -> dict:
    """新增角色标签"""
    name = tag_name.strip()
    if not name:
        return {"ok": False, "reason": "标签名不能为空"}
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "IF NOT EXISTS (SELECT 1 FROM role_tags WHERE tag_name = ?) INSERT INTO role_tags (tag_name, tag_color) VALUES (?, ?)",
        (name, name, tag_color)
    )
    return {"ok": True}


def delete_role_tag(tag_id: int) -> dict:
    """删除标签（同时清除角色关联）"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE staff_roles SET tag_id = NULL WHERE tag_id = ?", tag_id)
    cursor.execute("DELETE FROM role_tag_rel WHERE tag_id = ?", tag_id)
    cursor.execute("DELETE FROM staff_tags WHERE tag_id = ?", tag_id)
    cursor.execute("DELETE FROM role_tags WHERE tag_id = ?", tag_id)
    return {"ok": True}


def set_role_tag(role_id: int, tag_id: int) -> dict:
    """为角色设置标签（tag_id=0 表示清除）"""
    conn = get_connection()
    cursor = conn.cursor()
    if tag_id == 0:
        cursor.execute("UPDATE staff_roles SET tag_id = NULL WHERE role_id = ?", role_id)
    else:
        cursor.execute("UPDATE staff_roles SET tag_id = ? WHERE role_id = ?", tag_id, role_id)
    return {"ok": True}


def set_role_tags(role_id: int, tag_ids: list) -> dict:
    """为角色设置多个标签（tag_ids 为空列表表示清除全部）"""
    conn = get_connection()
    cursor = conn.cursor()
    # 清空该角色关联表
    cursor.execute("DELETE FROM role_tag_rel WHERE role_id = ?", role_id)
    for tid in tag_ids or []:
        cursor.execute(
            "IF NOT EXISTS (SELECT 1 FROM role_tag_rel WHERE role_id = ? AND tag_id = ?) "
            "INSERT INTO role_tag_rel (role_id, tag_id) VALUES (?, ?)",
            (role_id, tid, role_id, tid)
        )
    return {"ok": True}


# ========== 工单统计看板 ==========

def get_dashboard_stats(days: int = 7) -> dict:
    """
    工单统计看板聚合接口（支持时间范围筛选）
    参数：days - 统计最近 N 天的数据（默认 7 天）
    返回：kpi / trend_data / priority_distribution / status_distribution /
          efficiency_rank / avg_duration / sla_warning_list / recent_tickets
    """
    from datetime import datetime as _dt
    conn = get_connection()
    cursor = conn.cursor()

    today_str = _dt.now().strftime("%Y-%m-%d")

    # ---- 1) KPI 指标 ----
    # 1a) 工单总量
    cursor.execute("SELECT COUNT(*) FROM tickets")
    total_count = cursor.fetchone()[0] or 0

    # 1b) 今日新增
    cursor.execute("SELECT COUNT(*) FROM tickets WHERE CAST(create_time AS DATE) = ?", today_str)
    today_new = cursor.fetchone()[0] or 0

    # 1c) 已完成
    cursor.execute("SELECT COUNT(*) FROM tickets WHERE status = '已完成'")
    completed_count = cursor.fetchone()[0] or 0

    # 1d) 进行中
    cursor.execute("SELECT COUNT(*) FROM tickets WHERE status = '进行中'")
    in_progress_count = cursor.fetchone()[0] or 0

    # 1e) 未完成
    cursor.execute("SELECT COUNT(*) FROM tickets WHERE status = '未完成'")
    pending_count = cursor.fetchone()[0] or 0

    # 1f) 完成率
    completion_rate = round(completed_count / total_count * 100, 1) if total_count > 0 else 0.0

    # 1g) 平均响应时长（小时）
    cursor.execute(
        "SELECT CAST(AVG(DATEDIFF(MINUTE, create_time, COALESCE(updated_at, GETDATE()))) AS FLOAT) / 60.0 "
        "FROM tickets"
    )
    avg_hours = cursor.fetchone()[0]
    avg_response_hours = round(avg_hours, 1) if avg_hours else 0.0

    # 1h) SLA 超时 + 预警
    cursor.execute("SELECT config_value FROM sys_config WHERE config_key = 'sla_timeout_hours'")
    row = cursor.fetchone()
    sla_hours = float(row[0]) if row else 4.0

    cursor.execute("SELECT config_value FROM sys_config WHERE config_key = 'sla_warning_pct'")
    row = cursor.fetchone()
    sla_warning_pct = float(row[0]) if row else 75.0
    sla_warning_hours = sla_hours * sla_warning_pct / 100.0

    cursor.execute(
        "SELECT COUNT(*) FROM tickets "
        "WHERE priority = '高' AND status != '已完成' "
        "AND DATEDIFF(HOUR, create_time, GETDATE()) > ?",
        sla_hours
    )
    sla_overdue = cursor.fetchone()[0] or 0

    # ---- 2) N 天趋势 ----
    lookback = days - 1  # 包含今天
    cursor.execute(f"""
        SELECT CAST(create_time AS DATE) AS d,
               COUNT(*) AS total,
               SUM(CASE WHEN status = '已完成' THEN 1 ELSE 0 END) AS closed
        FROM tickets
        WHERE create_time >= DATEADD(DAY, -{lookback}, GETDATE())
        GROUP BY CAST(create_time AS DATE)
        ORDER BY d
    """)
    trend_rows = {str(r[0]): {"new": r[1], "closed": r[2]} for r in cursor.fetchall()}

    # 补齐缺失日期：生成从 days 天前到今天的完整日期列表，无数据的天填充 0
    from datetime import timedelta
    trend_data = []
    for i in range(days - 1, -1, -1):
        d = (_dt.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        if d in trend_rows:
            trend_data.append({"date": d, "new": trend_rows[d]["new"], "closed": trend_rows[d]["closed"]})
        else:
            trend_data.append({"date": d, "new": 0, "closed": 0})

    # ---- 3) 优先级分布 ----
    cursor.execute("SELECT priority, COUNT(*) FROM tickets GROUP BY priority")
    priority_distribution = {r[0]: r[1] for r in cursor.fetchall()}

    # ---- 4) 状态分布 ----
    cursor.execute("SELECT status, COUNT(*) FROM tickets GROUP BY status")
    status_distribution = {r[0]: r[1] for r in cursor.fetchall()}

    # ---- 5) 负责人效率排名 ----
    cursor.execute(
        "SELECT assignee, COUNT(*) AS done_count "
        "FROM tickets WHERE status = '已完成' "
        "GROUP BY assignee ORDER BY done_count DESC"
    )
    efficiency_rank = [
        {"assignee": r[0], "done_count": r[1], "rank": i + 1}
        for i, r in enumerate(cursor.fetchall())
    ]

    # ---- 6) 平均处理耗时（按优先级）----
    cursor.execute("""
        SELECT priority,
               CAST(AVG(DATEDIFF(MINUTE, create_time, COALESCE(updated_at, GETDATE()))) AS FLOAT) / 60.0
        FROM tickets WHERE status = '已完成'
        GROUP BY priority
    """)
    avg_duration = {r[0]: round(float(r[1]), 1) if r[1] is not None else 0.0 for r in cursor.fetchall()}

    # ---- 7) SLA 超时预警（含分级）----
    # 严重超时（已超过 sla_hours）
    cursor.execute(
        "SELECT id, title, priority, assignee, DATEDIFF(HOUR, create_time, GETDATE()) AS overdue_hours "
        "FROM tickets "
        "WHERE priority = '高' AND status != '已完成' "
        "AND DATEDIFF(HOUR, create_time, GETDATE()) >= ? "
        "ORDER BY overdue_hours DESC",
        sla_hours
    )
    sla_warning_list = [
        {"id": _fmt_tid(r[0]), "title": r[1], "priority": r[2], "assignee": r[3],
         "overdue_hours": r[4], "level": "critical"}
        for r in cursor.fetchall()
    ]

    # 预警（超过 sla_warning_hours 但未达到 sla_hours）
    cursor.execute(
        "SELECT id, title, priority, assignee, DATEDIFF(HOUR, create_time, GETDATE()) AS overdue_hours "
        "FROM tickets "
        "WHERE priority = '高' AND status != '已完成' "
        "AND DATEDIFF(HOUR, create_time, GETDATE()) >= ? "
        "AND DATEDIFF(HOUR, create_time, GETDATE()) < ? "
        "ORDER BY overdue_hours DESC",
        sla_warning_hours, sla_hours
    )
    warning_items = [
        {"id": _fmt_tid(r[0]), "title": r[1], "priority": r[2], "assignee": r[3],
         "overdue_hours": r[4], "level": "warning"}
        for r in cursor.fetchall()
    ]

    # 合并：严重超时在前，预警在后
    sla_warning_list = sla_warning_list + warning_items

    # ---- 8) 最近工单列表（供表格展示）----
    cursor.execute(
        "SELECT TOP 10 id, title, status, priority, assignee, create_time "
        "FROM tickets ORDER BY create_time DESC"
    )
    recent_tickets = [
        {"id": _fmt_tid(r[0]), "title": r[1], "status": r[2],
         "priority": r[3], "assignee": r[4], "create_time": _fmt_time(r[5])}
        for r in cursor.fetchall()
    ]

    return {
        "kpi": {
            "total_count": total_count,
            "today_new": today_new,
            "completed_count": completed_count,
            "in_progress_count": in_progress_count,
            "pending_count": pending_count,
            "completion_rate": completion_rate,
            "avg_response_hours": avg_response_hours,
            "sla_overdue": sla_overdue,
        },
        "trend_data": trend_data,
        "priority_distribution": priority_distribution,
        "status_distribution": status_distribution,
        "efficiency_rank": efficiency_rank,
        "avg_duration": avg_duration,
        "sla_warning_list": sla_warning_list,
        "recent_tickets": recent_tickets,
        "_meta": {"days": days, "sla_hours": sla_hours, "sla_warning_pct": sla_warning_pct},
    }


# ========== 一键初始化 ==========
def seed_all():
    print("=" * 50)
    print("[DB] 🚀 初始化数据库（近6个月模拟数据）...")
    print("=" * 50)
    try:
        init_database()
        seed_tickets()
        seed_metrics()
        seed_config_defaults()
        seed_staff_roles()
        seed_staff()
        seed_schedule()
        from seed_data_v2 import print_summary, generate_tickets, generate_schedule
        from datetime import date as _date
        START = _date(2026, 2, 1)
        END = _date.today()
        tickets = generate_tickets(START, END)
        schedules = generate_schedule(START, END)
        print_summary(tickets, schedules)
        print("[DB] 🎉 完成！")
    except Exception as e:
        print(f"[DB] ❌ 失败: {e}")
        raise


if __name__ == "__main__":
    seed_all()