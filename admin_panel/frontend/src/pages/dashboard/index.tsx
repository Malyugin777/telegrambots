import { useCustom } from '@refinedev/core';
import { Row, Col, Card, Statistic, Spin } from 'antd';
import {
  RobotOutlined,
  UserOutlined,
  MessageOutlined,
  NotificationOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import { Line } from '@ant-design/charts';

interface Stats {
  total_bots: number;
  active_bots: number;
  total_users: number;
  active_users_today: number;
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
      type: 'Messages',
    })) || []),
    ...(chart?.users?.map((item) => ({
      date: item.date,
      value: item.value,
      type: 'Active Users',
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
      <h1 style={{ marginBottom: '24px' }}>Dashboard</h1>

      {/* Stats Cards */}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={8} xl={4}>
          <Card className="stat-card">
            <Statistic
              title="Total Bots"
              value={stats?.total_bots || 0}
              prefix={<RobotOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>

        <Col xs={24} sm={12} lg={8} xl={4}>
          <Card className="stat-card">
            <Statistic
              title="Active Bots"
              value={stats?.active_bots || 0}
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>

        <Col xs={24} sm={12} lg={8} xl={4}>
          <Card className="stat-card">
            <Statistic
              title="Total Users"
              value={stats?.total_users || 0}
              prefix={<UserOutlined />}
              valueStyle={{ color: '#722ed1' }}
            />
          </Card>
        </Col>

        <Col xs={24} sm={12} lg={8} xl={4}>
          <Card className="stat-card">
            <Statistic
              title="DAU (Today)"
              value={stats?.active_users_today || 0}
              prefix={<UserOutlined />}
              valueStyle={{ color: '#13c2c2' }}
            />
          </Card>
        </Col>

        <Col xs={24} sm={12} lg={8} xl={4}>
          <Card className="stat-card">
            <Statistic
              title="Message Queue"
              value={stats?.messages_in_queue || 0}
              prefix={<MessageOutlined />}
              valueStyle={{ color: '#faad14' }}
            />
          </Card>
        </Col>

        <Col xs={24} sm={12} lg={8} xl={4}>
          <Card className="stat-card">
            <Statistic
              title="Broadcasts Running"
              value={stats?.broadcasts_running || 0}
              prefix={<NotificationOutlined />}
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
                <ClockCircleOutlined /> Activity (Last 7 Days)
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
