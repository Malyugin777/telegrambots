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
  DashboardOutlined,
} from '@ant-design/icons';
import { Area, Pie } from '@ant-design/charts';
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

interface FlyerStatsData {
  // Сегодня
  downloads_today: number;
  ad_offers_today: number;      // Уникальные юзеры
  subscribed_today: number;
  // За всё время
  downloads_total: number;
  ad_offers_total: number;
  subscribed_total: number;
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

  const { data: flyerStatsData } = useCustom<FlyerStatsData>({
    url: '/stats/flyer',
    method: 'get',
  });

  const stats = statsData?.data;
  const chart = chartData?.data;
  const platforms = platformData?.data?.platforms || [];
  const performance = performanceData?.data?.overall;
  const flyerStats = flyerStatsData?.data;

  // Показываем FlyerService виджет если есть скачивания
  const hasFlyerData = flyerStats && flyerStats.downloads_total > 0;

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

  // Цвета: Скачивания - синий, Новые юзеры - оранжевый (контрастные)
  const areaConfig = {
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
    color: ['#1890ff', '#fa8c16'],  // Синий и оранжевый
    theme: 'dark',
    areaStyle: () => {
      return {
        fillOpacity: 0.6,
      };
    },
    legend: {
      position: 'top' as const,
    },
    tooltip: {
      showMarkers: true,
      showTitle: true,
      shared: true,
    },
    xAxis: {
      label: {
        autoRotate: false,
        autoHide: true,
        style: {
          fill: '#999',
        },
      },
    },
    yAxis: {
      label: {
        style: {
          fill: '#999',
        },
      },
      grid: {
        line: {
          style: {
            stroke: '#333',
            lineWidth: 1,
            lineDash: [4, 4],
          },
        },
      },
    },
  };

  // Цвета платформ (яркие, различимые)
  const platformColors: Record<string, string> = {
    instagram: '#E1306C',
    tiktok: '#00f2ea',
    youtube: '#FF0000',
    youtube_full: '#FF0000',
    youtube_shorts: '#FF6B6B',
    pinterest: '#E60023',
  };

  // Фильтруем мусорные данные
  const pieData = platforms
    .filter((p: { name: string; count: number }) =>
      p.name !== '10' && p.count > 0 && p.name.length > 1
    )
    .map((p: { name: string; count: number }) => ({
      ...p,
      // Красивые названия
      displayName: p.name === 'youtube_full' ? 'YouTube Full' :
                   p.name === 'youtube_shorts' ? 'YouTube Shorts' :
                   p.name.charAt(0).toUpperCase() + p.name.slice(1),
    }));

  // Общее количество для центра
  const totalPlatformCount = pieData.reduce((sum: number, p: { count: number }) => sum + p.count, 0);

  const pieConfig = {
    data: pieData,
    angleField: 'count',
    colorField: 'name',
    radius: 0.75,
    innerRadius: 0.5,
    label: {
      type: 'spider' as const,
      content: (data: any) => `${data.displayName}\n${data.count}`,
      style: {
        fill: '#fff',
        fontSize: 13,
        fontWeight: 500,
      },
    },
    color: (datum: { name: string }) => platformColors[datum.name] || '#888',
    theme: 'dark',
    legend: false,  // Убираем легенду, все видно в лейблах
    statistic: {
      title: {
        offsetY: -4,
        style: {
          fontSize: '14px',
          fill: '#999',
        },
        content: 'Всего',
      },
      content: {
        offsetY: 4,
        style: {
          fontSize: '28px',
          fill: '#fff',
          fontWeight: 'bold',
        },
        content: totalPlatformCount.toString(),
      },
    },
    interactions: [
      { type: 'element-selected' },
      { type: 'element-active' },
    ],
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

      {/* Среднее время скачивания (без скорости и размера) */}
      {performance && (
        <Row gutter={[16, 16]} style={{ marginTop: '16px' }}>
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

      {/* FlyerService Stats */}
      {hasFlyerData && (
        <Row gutter={[16, 16]} style={{ marginTop: '16px' }}>
          <Col xs={24}>
            <Card
              title={
                <span>
                  <NotificationOutlined /> Реклама (каждое 10-е скачивание)
                </span>
              }
            >
              <Row gutter={[16, 16]}>
                {/* Сегодня */}
                <Col xs={24} sm={12}>
                  <div style={{ background: '#1a1a2e', padding: '16px', borderRadius: '8px' }}>
                    <h4 style={{ margin: '0 0 16px 0', color: '#fff' }}>Сегодня</h4>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#1890ff' }}></span>
                        <span style={{ color: '#888', flex: 1 }}>Скачиваний</span>
                        <span style={{ color: '#1890ff', fontWeight: 'bold', fontSize: '18px' }}>{flyerStats!.downloads_today}</span>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#faad14' }}></span>
                        <span style={{ color: '#888', flex: 1 }}>Предложено подписаться</span>
                        <span style={{ color: '#faad14', fontWeight: 'bold', fontSize: '18px' }}>{flyerStats!.ad_offers_today}</span>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#52c41a' }}></span>
                        <span style={{ color: '#888', flex: 1 }}>Подписалось</span>
                        <span style={{ color: '#52c41a', fontWeight: 'bold', fontSize: '18px' }}>{flyerStats!.subscribed_today}</span>
                      </div>
                    </div>
                  </div>
                </Col>

                {/* За всё время */}
                <Col xs={24} sm={12}>
                  <div style={{ background: '#1a1a2e', padding: '16px', borderRadius: '8px' }}>
                    <h4 style={{ margin: '0 0 16px 0', color: '#fff' }}>За всё время</h4>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#1890ff' }}></span>
                        <span style={{ color: '#888', flex: 1 }}>Скачиваний</span>
                        <span style={{ color: '#1890ff', fontWeight: 'bold', fontSize: '18px' }}>{flyerStats!.downloads_total}</span>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#faad14' }}></span>
                        <span style={{ color: '#888', flex: 1 }}>Предложено подписаться</span>
                        <span style={{ color: '#faad14', fontWeight: 'bold', fontSize: '18px' }}>{flyerStats!.ad_offers_total}</span>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#52c41a' }}></span>
                        <span style={{ color: '#888', flex: 1 }}>Подписалось</span>
                        <span style={{ color: '#52c41a', fontWeight: 'bold', fontSize: '18px' }}>{flyerStats!.subscribed_total}</span>
                      </div>
                    </div>
                  </div>
                </Col>
              </Row>
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
              <Area {...areaConfig} height={300} />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="По платформам">
            {pieData.length > 0 ? (
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
