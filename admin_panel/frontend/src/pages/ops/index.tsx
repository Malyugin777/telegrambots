import { useState, useEffect } from 'react';
import { useCustom } from '@refinedev/core';
import {
  Row,
  Col,
  Card,
  Statistic,
  Table,
  Tabs,
  Tag,
  Progress,
  Spin,
  Tooltip,
  Badge,
  Select,
} from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
  ThunderboltOutlined,
  CloudServerOutlined,
  DatabaseOutlined,
  ApiOutlined,
  WarningOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';

// ============ Types ============

interface PlatformStats {
  platform: string;
  total: number;
  success: number;
  errors: number;
  success_rate: number;
  p95_total_ms: number | null;
  p95_prep_ms: number | null;
  p95_download_ms: number | null;
  avg_speed_kbps: number | null;
  provider_share: Record<string, number>;
  top_error_class: string | null;
}

interface ProviderStats {
  provider: string;
  total: number;
  success: number;
  errors: number;
  success_rate: number;
  p95_total_ms: number | null;
  avg_speed_kbps: number | null;
  errors_by_class: Record<string, number>;
  cooldown_status: string | null;
  download_host_share: Record<string, number>;
  top_hosts: string[];
}

interface QuotaInfo {
  provider: string;
  plan: string;
  units_remaining: number | null;
  units_limit: number | null;
  requests_remaining: number | null;
  requests_limit: number | null;
  reset_hours: number | null;
  burn_rate_24h: number | null;
  burn_rate_7d: number | null;
  forecast_pessimistic: number | null;
  forecast_average: number | null;
}

interface SystemMetrics {
  cpu_percent: number | null;
  ram_percent: number | null;
  disk_percent: number | null;
  tmp_size_mb: number | null;
  active_downloads: number;
  active_uploads: number;
}

interface PlatformsResponse {
  range_hours: number;
  platforms: PlatformStats[];
}

interface ProvidersResponse {
  range_hours: number;
  providers: ProviderStats[];
}

interface QuotaResponse {
  updated_at: string;
  apis: QuotaInfo[];
}

interface SystemResponse {
  timestamp: string;
  metrics: SystemMetrics;
}

// ============ Helper Functions ============

const formatMs = (ms: number | null): string => {
  if (ms === null) return '-';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
};

const formatSpeed = (kbps: number | null): string => {
  if (kbps === null) return '-';
  if (kbps > 1000) return `${(kbps / 1000).toFixed(1)} MB/s`;
  return `${Math.round(kbps)} KB/s`;
};

const getSuccessRateColor = (rate: number): string => {
  if (rate >= 95) return '#52c41a';
  if (rate >= 80) return '#faad14';
  return '#ff4d4f';
};

// ============ Components ============

export const Ops = () => {
  const [timeRange, setTimeRange] = useState('24h');
  const [refreshKey, setRefreshKey] = useState(0);

  // Auto-refresh every 30 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      setRefreshKey((k) => k + 1);
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  // Fetch data
  const { data: platformsData, isLoading: platformsLoading } = useCustom<PlatformsResponse>({
    url: '/ops/platforms',
    method: 'get',
    config: { query: { range: timeRange } },
    queryOptions: { queryKey: ['ops-platforms', timeRange, refreshKey] },
  });

  const { data: providersData, isLoading: providersLoading } = useCustom<ProvidersResponse>({
    url: '/ops/providers',
    method: 'get',
    config: { query: { range: timeRange } },
    queryOptions: { queryKey: ['ops-providers', timeRange, refreshKey] },
  });

  const { data: quotaData, isLoading: quotaLoading } = useCustom<QuotaResponse>({
    url: '/ops/quota',
    method: 'get',
    queryOptions: { queryKey: ['ops-quota', refreshKey] },
  });

  const { data: systemData, isLoading: systemLoading } = useCustom<SystemResponse>({
    url: '/ops/system',
    method: 'get',
    queryOptions: { queryKey: ['ops-system', refreshKey] },
  });

  const platforms = platformsData?.data?.platforms || [];
  const providers = providersData?.data?.providers || [];
  const quotas = quotaData?.data?.apis || [];
  const system = systemData?.data?.metrics;

  // Calculate KPIs
  const totalSuccess = platforms.reduce((sum, p) => sum + p.success, 0);
  const totalErrors = platforms.reduce((sum, p) => sum + p.errors, 0);
  const overallSuccessRate = totalSuccess + totalErrors > 0
    ? (totalSuccess / (totalSuccess + totalErrors) * 100)
    : 0;

  const worstP95 = platforms.reduce((max, p) =>
    p.p95_total_ms && p.p95_total_ms > max ? p.p95_total_ms : max, 0);

  const savenowQuota = quotas.find(q => q.provider === 'savenow');

  // ============ Table Columns ============

  const platformColumns: ColumnsType<PlatformStats> = [
    {
      title: 'Platform',
      dataIndex: 'platform',
      key: 'platform',
      render: (platform: string) => (
        <Tag color={
          platform === 'youtube' ? 'red' :
          platform === 'instagram' ? 'magenta' :
          platform === 'tiktok' ? 'cyan' :
          platform === 'pinterest' ? 'volcano' : 'default'
        }>
          {platform.toUpperCase()}
        </Tag>
      ),
    },
    {
      title: 'Total',
      dataIndex: 'total',
      key: 'total',
      sorter: (a, b) => a.total - b.total,
    },
    {
      title: 'Success Rate',
      dataIndex: 'success_rate',
      key: 'success_rate',
      render: (rate: number) => (
        <span style={{ color: getSuccessRateColor(rate) }}>
          {rate.toFixed(1)}%
        </span>
      ),
      sorter: (a, b) => a.success_rate - b.success_rate,
    },
    {
      title: 'P95 Total',
      dataIndex: 'p95_total_ms',
      key: 'p95_total_ms',
      render: formatMs,
      sorter: (a, b) => (a.p95_total_ms || 0) - (b.p95_total_ms || 0),
    },
    {
      title: 'P95 Prep',
      dataIndex: 'p95_prep_ms',
      key: 'p95_prep_ms',
      render: formatMs,
    },
    {
      title: 'P95 Download',
      dataIndex: 'p95_download_ms',
      key: 'p95_download_ms',
      render: formatMs,
    },
    {
      title: 'Avg Speed',
      dataIndex: 'avg_speed_kbps',
      key: 'avg_speed_kbps',
      render: formatSpeed,
    },
    {
      title: 'Providers',
      dataIndex: 'provider_share',
      key: 'provider_share',
      render: (share: Record<string, number>) => (
        <div style={{ fontSize: '12px' }}>
          {Object.entries(share).map(([prov, pct]) => (
            <div key={prov}>
              <Tag color={prov === 'pytubefix' ? 'blue' : prov === 'rapidapi' ? 'green' : 'default'}>
                {prov}: {pct}%
              </Tag>
            </div>
          ))}
        </div>
      ),
    },
    {
      title: 'Top Error',
      dataIndex: 'top_error_class',
      key: 'top_error_class',
      render: (err: string | null) => err ? (
        <Tooltip title={err}>
          <Tag color="error">{err.slice(0, 15)}</Tag>
        </Tooltip>
      ) : '-',
    },
  ];

  const providerColumns: ColumnsType<ProviderStats> = [
    {
      title: 'Provider',
      dataIndex: 'provider',
      key: 'provider',
      render: (provider: string) => (
        <Tag color={
          provider === 'pytubefix' ? 'blue' :
          provider === 'rapidapi' ? 'green' :
          provider === 'ytdlp' ? 'purple' : 'default'
        }>
          {provider.toUpperCase()}
        </Tag>
      ),
    },
    {
      title: 'Total',
      dataIndex: 'total',
      key: 'total',
    },
    {
      title: 'Success Rate',
      dataIndex: 'success_rate',
      key: 'success_rate',
      render: (rate: number) => (
        <span style={{ color: getSuccessRateColor(rate) }}>
          {rate.toFixed(1)}%
        </span>
      ),
    },
    {
      title: 'P95 Total',
      dataIndex: 'p95_total_ms',
      key: 'p95_total_ms',
      render: formatMs,
    },
    {
      title: 'Avg Speed',
      dataIndex: 'avg_speed_kbps',
      key: 'avg_speed_kbps',
      render: formatSpeed,
    },
    {
      title: 'Download Hosts',
      dataIndex: 'download_host_share',
      key: 'download_host_share',
      render: (share: Record<string, number>, record: ProviderStats) => (
        <div style={{ fontSize: '12px' }}>
          {record.top_hosts.slice(0, 2).map(host => (
            <div key={host}>
              {host}: {share[host]?.toFixed(0) || 0}%
            </div>
          ))}
        </div>
      ),
    },
    {
      title: 'Errors by Class',
      dataIndex: 'errors_by_class',
      key: 'errors_by_class',
      render: (errors: Record<string, number>) => (
        <div style={{ fontSize: '12px' }}>
          {Object.entries(errors).slice(0, 3).map(([cls, count]) => (
            <Tag key={cls} color="error" style={{ marginBottom: '2px' }}>
              {cls}: {count}
            </Tag>
          ))}
        </div>
      ),
    },
  ];

  // ============ Render ============

  const isLoading = platformsLoading || providersLoading || quotaLoading || systemLoading;

  return (
    <div style={{ padding: '24px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <h1 style={{ margin: 0 }}>
          <ApiOutlined /> Ops Dashboard
        </h1>
        <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
          <Select
            value={timeRange}
            onChange={setTimeRange}
            style={{ width: 100 }}
            options={[
              { value: '1h', label: '1 hour' },
              { value: '24h', label: '24 hours' },
              { value: '7d', label: '7 days' },
            ]}
          />
          <Tooltip title="Auto-refresh: 30s">
            <Badge dot color={isLoading ? 'orange' : 'green'}>
              <ReloadOutlined spin={isLoading} style={{ fontSize: '18px' }} />
            </Badge>
          </Tooltip>
        </div>
      </div>

      {/* KPI Cards */}
      <Row gutter={[16, 16]} style={{ marginBottom: '24px' }}>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="Overall Success Rate"
              value={overallSuccessRate}
              precision={1}
              suffix="%"
              valueStyle={{ color: getSuccessRateColor(overallSuccessRate) }}
              prefix={overallSuccessRate >= 90 ? <CheckCircleOutlined /> : <WarningOutlined />}
            />
            <div style={{ fontSize: '12px', color: '#888', marginTop: '8px' }}>
              {totalSuccess} / {totalSuccess + totalErrors} downloads
            </div>
          </Card>
        </Col>

        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="Worst P95 Latency"
              value={worstP95 > 0 ? formatMs(worstP95) : '-'}
              valueStyle={{ color: worstP95 > 30000 ? '#ff4d4f' : worstP95 > 15000 ? '#faad14' : '#52c41a' }}
              prefix={<ClockCircleOutlined />}
            />
            <div style={{ fontSize: '12px', color: '#888', marginTop: '8px' }}>
              Across all platforms
            </div>
          </Card>
        </Col>

        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="Quota Forecast"
              value={savenowQuota?.forecast_average ?? '-'}
              suffix={savenowQuota?.forecast_average ? ' days' : ''}
              valueStyle={{
                color: (savenowQuota?.forecast_average ?? 999) < 3 ? '#ff4d4f' :
                       (savenowQuota?.forecast_average ?? 999) < 7 ? '#faad14' : '#52c41a'
              }}
              prefix={<DatabaseOutlined />}
            />
            <div style={{ fontSize: '12px', color: '#888', marginTop: '8px' }}>
              SaveNow @ {savenowQuota?.burn_rate_24h ?? 0} req/day
            </div>
          </Card>
        </Col>

        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="Active Operations"
              value={(system?.active_downloads ?? 0) + (system?.active_uploads ?? 0)}
              prefix={<ThunderboltOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
            <div style={{ fontSize: '12px', color: '#888', marginTop: '8px' }}>
              {system?.active_downloads ?? 0} downloads, {system?.active_uploads ?? 0} uploads
            </div>
          </Card>
        </Col>
      </Row>

      {/* Tabs */}
      <Tabs
        defaultActiveKey="platforms"
        items={[
          {
            key: 'platforms',
            label: (
              <span>
                <CloudServerOutlined /> Platforms
              </span>
            ),
            children: (
              <Card>
                {platformsLoading ? (
                  <div style={{ textAlign: 'center', padding: '40px' }}><Spin /></div>
                ) : (
                  <Table
                    dataSource={platforms}
                    columns={platformColumns}
                    rowKey="platform"
                    pagination={false}
                    size="middle"
                  />
                )}
              </Card>
            ),
          },
          {
            key: 'providers',
            label: (
              <span>
                <ApiOutlined /> Providers
              </span>
            ),
            children: (
              <Card>
                {providersLoading ? (
                  <div style={{ textAlign: 'center', padding: '40px' }}><Spin /></div>
                ) : (
                  <Table
                    dataSource={providers}
                    columns={providerColumns}
                    rowKey="provider"
                    pagination={false}
                    size="middle"
                  />
                )}
              </Card>
            ),
          },
          {
            key: 'system',
            label: (
              <span>
                <DatabaseOutlined /> System & Quota
              </span>
            ),
            children: (
              <Row gutter={[16, 16]}>
                {/* System Metrics */}
                <Col xs={24} lg={12}>
                  <Card title="System Metrics">
                    {systemLoading ? (
                      <Spin />
                    ) : system ? (
                      <div>
                        <div style={{ marginBottom: '16px' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                            <span>CPU</span>
                            <span>{system.cpu_percent?.toFixed(1) ?? '-'}%</span>
                          </div>
                          <Progress
                            percent={system.cpu_percent ?? 0}
                            showInfo={false}
                            strokeColor={system.cpu_percent && system.cpu_percent > 80 ? '#ff4d4f' : '#1890ff'}
                          />
                        </div>
                        <div style={{ marginBottom: '16px' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                            <span>RAM</span>
                            <span>{system.ram_percent?.toFixed(1) ?? '-'}%</span>
                          </div>
                          <Progress
                            percent={system.ram_percent ?? 0}
                            showInfo={false}
                            strokeColor={system.ram_percent && system.ram_percent > 80 ? '#ff4d4f' : '#52c41a'}
                          />
                        </div>
                        <div style={{ marginBottom: '16px' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                            <span>Disk</span>
                            <span>{system.disk_percent?.toFixed(1) ?? '-'}%</span>
                          </div>
                          <Progress
                            percent={system.disk_percent ?? 0}
                            showInfo={false}
                            strokeColor={system.disk_percent && system.disk_percent > 90 ? '#ff4d4f' : '#faad14'}
                          />
                        </div>
                        <div>
                          <span>/tmp size: </span>
                          <strong>{system.tmp_size_mb?.toFixed(1) ?? '-'} MB</strong>
                        </div>
                      </div>
                    ) : (
                      <div style={{ color: '#888' }}>No data available</div>
                    )}
                  </Card>
                </Col>

                {/* Quota Info */}
                <Col xs={24} lg={12}>
                  <Card title="API Quotas">
                    {quotaLoading ? (
                      <Spin />
                    ) : quotas.length > 0 ? (
                      <div>
                        {quotas.map((quota) => (
                          <Card
                            key={quota.provider}
                            size="small"
                            style={{ marginBottom: '12px' }}
                            title={
                              <span>
                                <Tag color={quota.provider === 'savenow' ? 'green' : 'blue'}>
                                  {quota.provider.toUpperCase()}
                                </Tag>
                                <span style={{ fontSize: '12px', color: '#888' }}>{quota.plan}</span>
                              </span>
                            }
                          >
                            <Row gutter={[16, 8]}>
                              <Col span={12}>
                                <div style={{ fontSize: '12px', color: '#888' }}>Units Remaining</div>
                                <div style={{ fontSize: '18px', fontWeight: 'bold' }}>
                                  {quota.units_remaining ?? '-'}
                                  {quota.units_limit && (
                                    <span style={{ fontSize: '12px', color: '#888' }}> / {quota.units_limit}</span>
                                  )}
                                </div>
                              </Col>
                              <Col span={12}>
                                <div style={{ fontSize: '12px', color: '#888' }}>Burn Rate (24h)</div>
                                <div style={{ fontSize: '18px', fontWeight: 'bold' }}>
                                  {quota.burn_rate_24h ?? '-'} <span style={{ fontSize: '12px' }}>req/day</span>
                                </div>
                              </Col>
                              <Col span={12}>
                                <div style={{ fontSize: '12px', color: '#888' }}>Forecast (avg)</div>
                                <div style={{
                                  fontSize: '18px',
                                  fontWeight: 'bold',
                                  color: (quota.forecast_average ?? 999) < 3 ? '#ff4d4f' :
                                         (quota.forecast_average ?? 999) < 7 ? '#faad14' : '#52c41a'
                                }}>
                                  {quota.forecast_average ?? '-'} <span style={{ fontSize: '12px' }}>days</span>
                                </div>
                              </Col>
                              <Col span={12}>
                                <div style={{ fontSize: '12px', color: '#888' }}>Forecast (pessimistic)</div>
                                <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#faad14' }}>
                                  {quota.forecast_pessimistic ?? '-'} <span style={{ fontSize: '12px' }}>days</span>
                                </div>
                              </Col>
                            </Row>
                            {quota.units_remaining !== null && quota.units_limit && (
                              <Progress
                                percent={Math.round((quota.units_remaining / quota.units_limit) * 100)}
                                strokeColor={{
                                  '0%': '#ff4d4f',
                                  '50%': '#faad14',
                                  '100%': '#52c41a',
                                }}
                                style={{ marginTop: '12px' }}
                              />
                            )}
                          </Card>
                        ))}
                      </div>
                    ) : (
                      <div style={{ color: '#888' }}>No quota data available</div>
                    )}
                  </Card>
                </Col>
              </Row>
            ),
          },
        ]}
      />
    </div>
  );
};
