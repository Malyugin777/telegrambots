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
} from '@ant-design/icons';
import { Line } from '@ant-design/charts';
import { useTranslation } from 'react-i18next';

interface Stats {
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

  const stats = statsData?.data;
  const chart = chartData?.data;

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

  if (statsLoading) {
    return (
      <div style={{ textAlign: 'center', padding: '50px' }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div style={{ padding: '24px' }}>
      <h1 style={{ marginBottom: '24px' }}>{t('dashboard.title')}</h1>

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

      {/* Load Chart */}
      <Row gutter={[16, 16]} style={{ marginTop: '24px' }}>
        <Col span={24}>
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
      </Row>
    </div>
  );
};
