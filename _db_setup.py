"""
数据库检查与还原工具
================================
由 startup.bat 调用，专注数据库就绪检查与自动还原。
用法：
  python _db_setup.py
  python _db_setup.py --restore-user sa --restore-password <密码>
"""
import os
import sys
import argparse

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_SERVER = "127.0.0.1"
DB_NAME = "OpsCenter"
DB_USER = "ai_ops_user"
DB_PASSWORD = "Ops1234"
DB_DRIVER = "{ODBC Driver 17 for SQL Server}"


def _conn_str(database, user=None, password=None):
    u = user or DB_USER
    p = password or DB_PASSWORD
    return (
        f"DRIVER={DB_DRIVER};SERVER={DB_SERVER};DATABASE={database};"
        f"UID={u};PWD={p};TrustServerCertificate=yes"
    )


def check_db_ready():
    """检查数据库是否可连接且有数据。返回 (ready: bool, message: str)"""
    try:
        import pyodbc
        conn = pyodbc.connect(_conn_str(DB_NAME), timeout=5)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM tickets")
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        if count > 0:
            return True, f"数据库 {DB_NAME} 连接正常，已有 {count} 条工单数据，跳过还原。"
        else:
            return False, f"数据库 {DB_NAME} 可连接，但 tickets 表为空，请先还原数据库备份。"
    except Exception as e:
        return False, f"无法连接数据库 {DB_NAME}：{e}"


def restore_database(restore_user, restore_password):
    """从备份文件还原数据库"""
    backup = os.path.join(ROOT, "OpsCenter.bak")
    if not os.path.exists(backup):
        print(f"  [错误] 未找到备份文件 OpsCenter.bak，请将其放到项目根目录。")
        return False
    print(f"  [还原] 正在从备份文件还原数据库 {DB_NAME}（可能需要 1-2 分钟）...")
    try:
        import pyodbc
        conn = pyodbc.connect(
            _conn_str("master", restore_user, restore_password), autocommit=True, timeout=10
        )
        cursor = conn.cursor()
        cursor.execute(f"RESTORE DATABASE {DB_NAME} FROM DISK = ? WITH REPLACE, RECOVERY", (backup,))
        cursor.close()
        conn.close()
        print(f"  [还原] 数据库还原成功。")
        return True
    except Exception as e:
        print(f"  [错误] 数据库还原失败：{e}")
        print(f"  [提示] 还原数据库需要 sysadmin / dbcreator 权限，")
        print(f"         请使用 SSMS 以管理员身份手动还原 OpsCenter.bak，")
        print(f"         或为当前用户授予 dbcreator 权限后重试。")
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--restore-user", default=DB_USER)
    parser.add_argument("--restore-password", default=DB_PASSWORD)
    args = parser.parse_args()

    print("=" * 56)
    print("  [数据库] 检查数据库状态...")
    print("=" * 56)

    ready, msg = check_db_ready()
    print(f"  {msg}")

    if ready:
        sys.exit(0)

    # 不可连接 → 尝试还原
    if "可连接" in msg:
        # 表为空 → 需要还原
        print(f"  [操作] 数据库已连接但无数据，尝试还原备份...")
    else:
        # 无法连接 → 尝试还原
        print(f"  [操作] 数据库无法连接，尝试从备份还原...")

    if restore_database(args.restore_user, args.restore_password):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()