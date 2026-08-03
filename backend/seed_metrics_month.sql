-- ============================================
-- 第一步：为 metrics_snapshots 表添加高级监控字段
-- ============================================
USE OpsCenter;
GO

ALTER TABLE dbo.metrics_snapshots ADD
    -- 应用与服务质量 (QoS)
    api_latency_ms        FLOAT    NULL,   -- 接口平均响应延时 (ms)
    error_rate_percent    FLOAT    NULL,   -- HTTP 错误率 (%)
    qps_or_tps            FLOAT    NULL,   -- 每秒请求数 / 事务数
    -- 算力与异构资源 (GPU/容器)
    gpu_usage_percent     FLOAT    NULL,   -- GPU 负载 (%)
    gpu_temp_celsius      FLOAT    NULL,   -- GPU 核心温度 (°C)
    container_active_count INT     NULL,   -- 活跃容器数
    -- 网络深度状态 (TCP/安全)
    tcp_established        INT     NULL,   -- 活跃 TCP 连接数
    security_intercept_count INT  NULL,   -- WAF/防火墙拦截次数
    -- 全局健康度
    health_score          FLOAT    NULL;   -- 综合健康评分 (0-100)

PRINT '✅ 字段已添加，共 9 个新列';

-- ============================================
-- 第二步：清空旧数据并重新插入 30 天完整快照
-- ============================================
DELETE FROM dbo.metrics_snapshots;
DBCC CHECKIDENT ('dbo.metrics_snapshots', RESEED, 0);
PRINT '✅ 旧数据已清空，开始生成历史快照...';
GO

-- 基础基准值
DECLARE @base_cpu          FLOAT = 67.3;
DECLARE @base_mem          FLOAT = 72.5;
DECLARE @base_disk         FLOAT = 55.8;
DECLARE @base_net_in       FLOAT = 125.4;
DECLARE @base_net_out      FLOAT = 89.2;
DECLARE @base_disk_read    FLOAT = 45.6;
DECLARE @base_disk_write   FLOAT = 32.1;

-- 新增字段的基准值
DECLARE @base_latency      FLOAT = 120;     -- 延时基线 120ms
DECLARE @base_qps          FLOAT = 850;     -- QPS 基线 850
DECLARE @base_gpu          FLOAT = 45;      -- GPU 基线 45%
DECLARE @base_gpu_temp     FLOAT = 55;      -- GPU 温度基线 55°C
DECLARE @base_containers   INT    = 12;     -- 活跃容器基线 12
DECLARE @base_tcp          INT    = 600;    -- TCP 连接基线 600

DECLARE @start_time DATETIME2 = DATEADD(DAY, -30, GETDATE());

;WITH TenMinSlots AS (
    SELECT TOP 4320
        DATEADD(MINUTE, (ROW_NUMBER() OVER (ORDER BY a.object_id) - 1) * 10, @start_time) AS snapshot_time,
        ROW_NUMBER() OVER (ORDER BY a.object_id) AS rn,
        CHECKSUM(NEWID()) AS rnd,
        ABS(CHECKSUM(NEWID())) % 1000 AS rnd2,
        ABS(CHECKSUM(NEWID())) % 1000 AS rnd3
    FROM sys.all_objects a
    CROSS JOIN sys.all_objects b
)
INSERT INTO dbo.metrics_snapshots
    (cpu_usage_percent, memory_usage_percent, disk_usage_percent,
     network_in_mbps, network_out_mbps, disk_read_mbps, disk_write_mbps,
     -- 新增字段
     api_latency_ms, error_rate_percent, qps_or_tps,
     gpu_usage_percent, gpu_temp_celsius, container_active_count,
     tcp_established, security_intercept_count, health_score,
     snapshot_time)
SELECT
    -- ========== 原有字段 ==========
    -- CPU: 正弦日间波动 + 随机噪声
    ROUND(@base_cpu + 10 * SIN(2 * PI() * s.rn / 144.0) + (s.rnd % 500) / 100.0 - 2.5, 1),

    -- 内存: 缓慢爬升 + 正弦波动
    ROUND(@base_mem + 3 * SIN(2 * PI() * s.rn / 300.0) + (s.rnd % 300) / 100.0 - 1.5 + s.rn * 0.0005, 1),

    -- 磁盘: 平稳 + 随机
    ROUND(@base_disk + (s.rnd % 600) / 100.0 - 3.0, 1),

    -- 网络入: 日间波峰
    ROUND(@base_net_in + 20 * SIN(2 * PI() * s.rn / 72.0) + (s.rnd % 1500) / 100.0 - 7.5, 1),

    -- 网络出
    ROUND(@base_net_out + 15 * SIN(2 * PI() * s.rn / 72.0 + 0.5) + (s.rnd % 1200) / 100.0 - 6.0, 1),

    -- 磁盘读
    ROUND(@base_disk_read + (s.rnd % 800) / 100.0 - 4.0, 1),

    -- 磁盘写
    ROUND(@base_disk_write + (s.rnd % 600) / 100.0 - 3.0, 1),

    -- ========== 新增字段 ==========

    -- API 延时 (ms): 基线 120ms, 日间升高, 偶发尖刺
    ROUND(
        @base_latency
        + 15 * SIN(2 * PI() * s.rn / 72.0)
        + CASE WHEN s.rnd2 > 980 THEN 200 + (s.rnd3 % 200)
               ELSE (s.rnd % 600) / 100.0 - 3.0 END
    , 1),

    -- 错误率 (%): 基线 0.5%
    ROUND(
        CASE
            WHEN s.rnd2 > 990 THEN 2.0 + (s.rnd3 % 300) / 100.0
            WHEN s.rnd2 > 970 THEN 0.8 + (s.rnd3 % 100) / 100.0
            ELSE 0.3 + (s.rnd % 50) / 100.0
        END
    , 2),

    -- QPS: 基线 850, 日间 1500+, 夜间 300-
    ROUND(
        CASE
            WHEN (s.rn % 72) BETWEEN 0 AND 48
            THEN @base_qps + 700 * SIN(PI() * (s.rn % 72) / 48.0) + (s.rnd % 2000) / 100.0 - 10.0
            ELSE 300 + (s.rnd % 5000) / 100.0
        END
    , 1),

    -- GPU 负载 (%): 基线 45%
    ROUND(
        @base_gpu + 15 * SIN(2 * PI() * s.rn / 200.0 + 1.2) + (s.rnd % 800) / 100.0 - 4.0
    , 1),

    -- GPU 温度 (°C): 与 GPU 负载正相关
    ROUND(
        @base_gpu_temp + 0.15 * (
            @base_gpu + 15 * SIN(2 * PI() * s.rn / 200.0 + 1.2) + (s.rnd % 800) / 100.0 - 4.0
        ) + (s.rnd % 200) / 100.0 - 1.0
    , 1),

    -- 活跃容器数: 基本稳定 10-15
    CASE
        WHEN s.rnd2 > 995 THEN @base_containers + 3
        WHEN s.rnd2 > 990 THEN @base_containers - 2
        ELSE @base_containers + (s.rnd % 5) - 2
    END,

    -- TCP 连接数: 与 QPS 正相关
    ROUND(
        300 + 0.6 * (
            CASE
                WHEN (s.rn % 72) BETWEEN 0 AND 48
                THEN @base_qps + 700 * SIN(PI() * (s.rn % 72) / 48.0) + (s.rnd % 2000) / 100.0 - 10.0
                ELSE 300 + (s.rnd % 5000) / 100.0
            END
        ) + (s.rnd % 2000) / 100.0 - 10.0
    , 0),

    -- 安全拦截次数: 大部分为 0
    CASE
        WHEN s.rnd2 > 995 THEN 8 + (s.rnd3 % 80) / 10
        WHEN s.rnd2 > 985 THEN 2 + (s.rnd3 % 30) / 10
        ELSE 0
    END,

    -- 健康评分 (0-100)
    ROUND(
        100
        - CASE WHEN @base_cpu + 10 * SIN(2 * PI() * s.rn / 144.0) + (s.rnd % 500) / 100.0 - 2.5 > 90 THEN 8 ELSE 0 END
        - CASE WHEN @base_mem + 3 * SIN(2 * PI() * s.rn / 300.0) + (s.rnd % 300) / 100.0 - 1.5 + s.rn * 0.0005 > 95 THEN 5 ELSE 0 END
        - CASE
            WHEN @base_latency + 15 * SIN(2 * PI() * s.rn / 72.0) + CASE WHEN s.rnd2 > 980 THEN 200 ELSE (s.rnd % 600) / 100.0 - 3.0 END > 300
            THEN 10 ELSE 0 END
        - CASE
            WHEN CASE
                WHEN s.rnd2 > 990 THEN 2.0 + (s.rnd3 % 300) / 100.0
                WHEN s.rnd2 > 970 THEN 0.8 + (s.rnd3 % 100) / 100.0
                ELSE 0.3 + (s.rnd % 50) / 100.0
            END > 2
            THEN 12 ELSE 0 END
        - (s.rnd % 20) / 100.0
    , 1) AS health_score,

    s.snapshot_time
FROM TenMinSlots s;

PRINT CONCAT('🎉 成功生成 ', @@ROWCOUNT, ' 条完整监控快照数据！');
PRINT '   时间范围：过去 30 天，每 10 分钟一条';
PRINT '   新增字段：api_latency_ms / error_rate_percent / qps_or_tps';
PRINT '            gpu_usage_percent / gpu_temp_celsius / container_active_count';
PRINT '            tcp_established / security_intercept_count / health_score';
PRINT '✅ 请刷新 SSMS 中 dbo.metrics_snapshots 表查看。';
GO
