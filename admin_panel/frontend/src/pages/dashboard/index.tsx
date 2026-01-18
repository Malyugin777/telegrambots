import { useCustom } from '@refinedev/core';
import { Row, Col, Card, Statistic, Spin } from 'antd';
import {
  RobotOutlined,
  UserOutlined,
  DownloadOutlined,
  NotificationOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  FireOutlined,
  ThunderboltOutlined,
  FileOutlined,
  DashboardOutlined,
} from '@ant-design/icons';
import { Line, Pie } from '@ant-design/charts';
import { useTranslation } from 'react-i18next';

interface Stats {
  version: string;
  total_bots: number;
  active_bots: number;
  total_users: number;
  active_users_today: number;
  downloads_today: number;
  total_downloads: number;
  messages_in_queue: number;
  broadcasts_running: number;
}

interface ChartDataPoint {
  date: string;
  value: number;
}

interface ChartData {
  messages: ChartDataPoint[];
  users: ChartDataPoint[];
}

interface PlatformData {
  platforms: Array<{ name: string; count: number }>;
}

interface PlatformPerformance {
  platform: string;
  avg_download_time_ms: number | null;
  avg_file_size_mb: number | null;
  avg_speed_kbps: number | null;
  total_downloads: number;
}

interface PerformanceData {
  overall: PlatformPerformance;
  platforms: PlatformPerformance[];
}

export const Dashboard = () => {
  const { t } = useTranslation();

  const { data: statsData, isLoading: statsLoading } = useCustom<Stats>({
    url: '/stats',
    method: 'get',
  });

  const { data: chartData, isLoading: chartLoading } = useCustom<ChartData>({
    url: '/stats/chart',
    method: 'get',
    config: {
      query: { days: 7 },
    },
  });

  const { data: platformData } = useCustom<PlatformData>({
    url: '/stats/platforms',
    method: 'get',
  });

  const { data: performanceData } = useCustom<PerformanceData>({
    url: '/stats/performance',
    method: 'get',
  });

  const stats = statsData?.data;
  const chart = chartData?.data;
  const platforms = platformData?.data?.platforms || [];
  const performance = performanceData?.data?.overall;

  // Prepare chart data
  const lineData = [
    ...(chart?.messages?.map((item) => ({
      date: item.date,
      value: item.value,
      type: t('dashboard.chartDownloads'),
    })) || []),
    ...(chart?.users?.map((item) => ({
      date: item.date,
      value: item.value,
      type: t('dashboard.chartNewUsers'),
    })) || []),
  ];

  const lineConfig = {
    data: lineData,
    xField: 'date',
    yField: 'value',
    seriesField: 'type',
    smooth: true,
    animation: {
      appear: {
        animation: 'path-in',
        duration: 1000,
      },
    },
    color: ['#1890ff', '#52c41a'],
    theme: 'dark',
  };

  const platformColors: Record<string, string> = {
    instagram: '#E1306C',
    tiktok: '#00f2ea',
    youtube: '#FF0000',
    pinterest: '#E60023',
  };

  const pieConfig = {
    data: platforms,
    angleField: 'count',
    colorField: 'name',
    radius: 0.8,
    innerRadius: 0.6,
    label: {
      type: 'outer',
      content: '{name}: {value}',
    },
    color: platforms.map((p: { name: string }) => platformColors[p.name] || '#888'),
    theme: 'dark',
    legend: {
      position: 'bottom' as const,
    },
  };

  if (statsLoading) {
    return (
      <div style={{ textAlign: 'center', padding: '50px' }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div style={{ padding: '24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <h1 style={{ margin: 0 }}>{t('dashboard.title')}</h1>
        {stats?.version && (
          <span style={{ color: '#888', fontSize: '14px' }}>v{stats.version}</span>
        )}
      </div>

      {/* Stats Cards */}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={8} xl={4}>
          <Card className="stat-card">
            <Statistic
              title={t('dashboard.totalBots')}
              value={stats?.total_bots || 0}
              prefix={<RobotOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>

        <Col xs={24} sm={12} lg={8} xl={4}>
          <Card className="stat-card">
            <Statistic
              title={t('dashboard.activeBots')}
              value={stats?.active_bots || 0}
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>

        <Col xs={24} sm={12} lg={8} xl={4}>
          <Card className="stat-card">
            <Statistic
              title={t('dashboard.totalUsers')}
              value={stats?.total_users || 0}
              prefix={<UserOutlined />}
              valueStyle={{ color: '#722ed1' }}
            />
          </Card>
        </Col>

        <Col xs={24} sm={12} lg={8} xl={4}>
          <Card className="stat-card">
            <Statistic
              title={t('dashboard.dauToday')}
              value={stats?.active_users_today || 0}
              prefix={<UserOutlined />}
              valueStyle={{ color: '#13c2c2' }}
            />
          </Card>
        </Col>

        <Col xs={24} sm={12} lg={8} xl={4}>
          <Card className="stat-card">
            <Statistic
              title={t('dashboard.downloadsToday')}
              value={stats?.downloads_today || 0}
              prefix={<FireOutlined />}
              valueStyle={{ color: '#fa541c' }}
            />
          </Card>
        </Col>

        <Col xs={24} sm={12} lg={8} xl={4}>
          <Card className="stat-card">
            <Statistic
              title={t('dashboard.totalDownloads')}
              value={stats?.total_downloads || 0}
              prefix={<DownloadOutlined />}
              valueStyle={{ color: '#eb2f96' }}
            />
          </Card>
        </Col>
      </Row>

      {/* Performance Cards */}
      {performance && (
        <Row gutter={[16, 16]} style={{ marginTop: '16px' }}>
          <Col xs={24} sm={8}>
            <Card className="stat-card">
              <Statistic
                title="Средняя скорость"
                value={performance.avg_speed_kbps ? Math.round(performance.avg_speed_kbps) : 0}
                suffix="KB/s"
                prefix={<ThunderboltOutlined />}
                valueStyle={{ color: '#faad14' }}
              />
            </Card>
          </Col>

          <Col xs={24} sm={8}>
            <Card className="stat-card">
              <Statistic
                title="Средний размер файла"
                value={performance.avg_file_size_mb ? performance.avg_file_size_mb.toFixed(2) : '0.00'}
                suffix="MB"
                prefix={<FileOutlined />}
                valueStyle={{ color: '#1890ff' }}
              />
            </Card>
          </Col>

          <Col xs={24} sm={8}>
            <Card className="stat-card">
              <Statistic
                title="Среднее время скачивания"
                value={performance.avg_download_time_ms ? Math.round(performance.avg_download_time_ms / 1000) : 0}
                suffix="сек"
                prefix={<DashboardOutlined />}
                valueStyle={{ color: '#52c41a' }}
              />
            </Card>
          </Col>
        </Row>
      )}

      {/* Charts Row */}
      <Row gutter={[16, 16]} style={{ marginTop: '24px' }}>
        <Col xs={24} lg={16}>
          <Card
            title={
              <span>
                <ClockCircleOutlined /> {t('dashboard.activityChart')}
              </span>
            }
          >
            {chartLoading ? (
              <div style={{ textAlign: 'center', padding: '50px' }}>
                <Spin />
              </div>
            ) : (
              <Line {...lineConfig} height={300} />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="По платформам">
            {platforms.length > 0 ? (
              <Pie {...pieConfig} height={300} />
            ) : (
              <div style={{ textAlign: 'center', padding: '50px', color: '#888' }}>
                Нет данных
              </div>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
};
