import { useState, useEffect } from 'react';
import { useCustom, useApiUrl } from '@refinedev/core';
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
  Switch,
  Button,
  Segmented,
  message,
} from 'antd';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  ThunderboltOutlined,
  CloudServerOutlined,
  DatabaseOutlined,
  ApiOutlined,
  WarningOutlined,
  ReloadOutlined,
  PauseCircleOutlined,
  ArrowUpOutlined,
  ArrowDownOutlined,
  SaveOutlined,
  UndoOutlined,
  BranchesOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';

// ============ Types ============

interface PlatformStats {
  platform: string;
  bucket: string | null;
  total: number;
  success: number;
  errors: number;
  success_rate: number;
  p95_total_ms: number | null;
  p95_prep_ms: number | null;
  p95_download_ms: number | null;
  p95_upload_ms: number | null;
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
  enabled: boolean;
  cooldown_until: string | null;
  health: string;
  download_host_share: Record<string, number>;
  top_hosts: string[];
  last_success_at: string | null;
  last_error_at: string | null;
  last_error_class: string | null;
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
  // RAM
  ram_percent: number | null;
  ram_used_bytes: number | null;
  ram_total_bytes: number | null;
  // Disk
  disk_percent: number | null;
  disk_used_bytes: number | null;
  disk_total_bytes: number | null;
  // /tmp
  tmp_used_bytes: number | null;
  // Active operations
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

// Routing types
interface ProviderConfig {
  name: string;
  enabled: boolean;
  timeout_sec: number;
}

interface RoutingConfig {
  source: string;
  chain: ProviderConfig[];
  available_providers: string[];
  has_override: boolean;
  override_expires_at: string | null;
}

interface RoutingListResponse {
  sources: RoutingConfig[];
}

// Human-readable source names
const SOURCE_LABELS: Record<string, string> = {
  youtube_full: 'YouTube (Full)',
  youtube_shorts: 'YouTube Shorts',
  instagram_reel: 'Instagram Reels',
  instagram_post: 'Instagram Post',
  instagram_story: 'Instagram Story',
  instagram_carousel: 'Instagram Carousel',
  tiktok: 'TikTok',
  pinterest: 'Pinterest',
};

// Provider labels
const PROVIDER_LABELS: Record<string, string> = {
  ytdlp: 'yt-dlp',
  pytubefix: 'pytubefix',
  savenow: 'SaveNow API',
  rapidapi: 'RapidAPI',
};

const PROVIDER_COLORS: Record<string, string> = {
  ytdlp: 'purple',
  pytubefix: 'blue',
  savenow: 'orange',
  rapidapi: 'green',
};

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

const formatBytes = (bytes: number | null): string => {
  if (bytes === null) return '-';
  const gb = bytes / (1024 * 1024 * 1024);
  if (gb >= 1) return `${gb.toFixed(1)} GB`;
  const mb = bytes / (1024 * 1024);
  return `${mb.toFixed(0)} MB`;
};

// Human-readable source labels for platform:bucket combinations
const getSourceLabel = (platform: string, bucket: string | null): string => {
  if (!bucket) {
    // Platform-only mode
    const platformLabels: Record<string, string> = {
      youtube: 'YouTube',
      instagram: 'Instagram',
      tiktok: 'TikTok',
      pinterest: 'Pinterest',
    };
    return platformLabels[platform] || platform;
  }

  // Platform + bucket mode - human-readable labels
  const labels: Record<string, Record<string, string>> = {
    youtube: {
      shorts: 'YouTube Shorts',
      full: 'YouTube (Full)',
      long: 'YouTube (Full)',  // legacy bucket name
      medium: 'YouTube (Medium)',
    },
    instagram: {
      reel: 'Instagram Reels',
      post: 'Instagram Post',
      carousel: 'Instagram Carousel',
      story: 'Instagram Story',
      photo: 'Instagram Photo',
    },
    tiktok: {
      video: 'TikTok',
    },
    pinterest: {
      video: 'Pinterest Video',
      photo: 'Pinterest Photo',
    },
  };

  return labels[platform]?.[bucket] || `${platform}:${bucket}`;
};

const getSourceColor = (platform: string): string => {
  const colors: Record<string, string> = {
    youtube: 'red',
    instagram: 'magenta',
    tiktok: 'cyan',
    pinterest: 'volcano',
  };
  return colors[platform] || 'default';
};

const formatTimeAgo = (isoDate: string | null): string => {
  if (!isoDate) return '-';
  const date = new Date(isoDate);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  const diffHour = Math.floor(diffMin / 60);

  if (diffMin < 1) return 'только что';
  if (diffMin < 60) return `${diffMin}м назад`;
  if (diffHour < 24) return `${diffHour}ч назад`;
  return `${Math.floor(diffHour / 24)}д назад`;
};

const getHealthBadge = (health: string) => {
  switch (health) {
    case 'healthy':
      return <Badge status="success" text="OK" />;
    case 'degraded':
      return <Badge status="warning" text="Degraded" />;
    case 'down':
      return <Badge status="error" text="Down" />;
    default:
      return <Badge status="default" text="Unknown" />;
  }
};

const P95Tooltip = ({ children }: { children: React.ReactNode }) => (
  <Tooltip title="95% загрузок быстрее этого времени">
    {children}
  </Tooltip>
);

// ============ Components ============

export const Ops = () => {
  const [timeRange, setTimeRange] = useState('24h');
  const [groupBy, setGroupBy] = useState<'platform' | 'bucket'>('platform');
  const [refreshKey, setRefreshKey] = useState(0);
  const apiUrl = useApiUrl();

  // Auto-refresh every 30 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      setRefreshKey((k) => k + 1);
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  // Fetch data
  const { data: platformsData, isLoading: platformsLoading, refetch: refetchPlatforms } = useCustom<PlatformsResponse>({
    url: '/ops/platforms',
    method: 'get',
    config: { query: { range: timeRange, group_by: groupBy } },
    queryOptions: { queryKey: ['ops-platforms', timeRange, groupBy, refreshKey] },
  });

  const { data: providersData, isLoading: providersLoading, refetch: refetchProviders } = useCustom<ProvidersResponse>({
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

  // Routing data
  const { data: routingData, isLoading: routingLoading, refetch: refetchRouting } = useCustom<RoutingListResponse>({
    url: '/ops/routing',
    method: 'get',
    queryOptions: { queryKey: ['ops-routing', refreshKey] },
  });

  // State for routing editor
  const [selectedSource, setSelectedSource] = useState<string>('youtube_full');
  const [editedChain, setEditedChain] = useState<ProviderConfig[] | null>(null);
  const [routingSaving, setRoutingSaving] = useState(false);

  const platforms = platformsData?.data?.platforms || [];
  const providers = providersData?.data?.providers || [];
  const quotas = quotaData?.data?.apis || [];
  const system = systemData?.data?.metrics;
  const routingSources = routingData?.data?.sources || [];

  // Calculate KPIs
  const totalSuccess = platforms.reduce((sum, p) => sum + p.success, 0);
  const totalErrors = platforms.reduce((sum, p) => sum + p.errors, 0);
  const overallSuccessRate = totalSuccess + totalErrors > 0
    ? (totalSuccess / (totalSuccess + totalErrors) * 100)
    : 0;

  const worstP95 = platforms.reduce((max, p) =>
    p.p95_total_ms && p.p95_total_ms > max ? p.p95_total_ms : max, 0);

  const savenowQuota = quotas.find(q => q.provider === 'savenow');
  const socialQuota = quotas.find(q => q.provider === 'social_download');

  // Calculate projected usage for social_download (main API)
  const socialRemaining = socialQuota?.requests_remaining;
  const socialLimit = socialQuota?.requests_limit;
  const socialResetHours = socialQuota?.reset_hours;
  const socialDaysUntilReset = socialResetHours ? Math.ceil(socialResetHours / 24) : null;
  const socialProjectedUsage = socialQuota?.burn_rate_24h && socialDaysUntilReset
    ? Math.round(socialQuota.burn_rate_24h * socialDaysUntilReset)
    : null;
  const socialProjectedPercent = socialProjectedUsage && socialLimit
    ? Math.round((socialProjectedUsage / socialLimit) * 100)
    : null;
  const socialUsedPercent = socialRemaining !== null && socialRemaining !== undefined && socialLimit
    ? Math.round(((socialLimit - socialRemaining) / socialLimit) * 100)
    : null;

  // Provider control handlers
  const handleToggleProvider = async (provider: string, enabled: boolean) => {
    try {
      const endpoint = enabled ? 'enable' : 'disable';
      await fetch(`${apiUrl}/ops/providers/${provider}/${endpoint}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
        },
      });
      message.success(`${provider} ${enabled ? 'enabled' : 'disabled'}`);
      refetchProviders();
    } catch {
      message.error('Failed to update provider state');
    }
  };

  const handleCooldown = async (provider: string, minutes: number) => {
    try {
      await fetch(`${apiUrl}/ops/providers/${provider}/cooldown?minutes=${minutes}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
        },
      });
      message.success(`${provider} in cooldown for ${minutes} minutes`);
      refetchProviders();
    } catch {
      message.error('Failed to set cooldown');
    }
  };

  // Routing handlers
  const currentRouting = routingSources.find(r => r.source === selectedSource);
  const displayChain = editedChain || currentRouting?.chain || [];

  const handleMoveProvider = (index: number, direction: 'up' | 'down') => {
    const chain = [...displayChain];
    const newIndex = direction === 'up' ? index - 1 : index + 1;
    if (newIndex < 0 || newIndex >= chain.length) return;
    [chain[index], chain[newIndex]] = [chain[newIndex], chain[index]];
    setEditedChain(chain);
  };

  const handleToggleProviderInChain = (index: number) => {
    const chain = [...displayChain];
    chain[index] = { ...chain[index], enabled: !chain[index].enabled };
    setEditedChain(chain);
  };

  const handleSaveRouting = async () => {
    if (!editedChain) return;
    setRoutingSaving(true);
    try {
      const response = await fetch(`${apiUrl}/ops/routing/${selectedSource}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ chain: editedChain }),
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `HTTP ${response.status}`);
      }
      message.success('Routing saved');
      setEditedChain(null);
      refetchRouting();
    } catch (err) {
      message.error(`Failed to save routing: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
    setRoutingSaving(false);
  };

  const handleResetRouting = async () => {
    setRoutingSaving(true);
    try {
      await fetch(`${apiUrl}/ops/routing/${selectedSource}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
        },
      });
      message.success('Routing reset to default');
      setEditedChain(null);
      refetchRouting();
    } catch {
      message.error('Failed to reset routing');
    }
    setRoutingSaving(false);
  };

  const handleClearOverride = async () => {
    try {
      await fetch(`${apiUrl}/ops/routing/${selectedSource}/override`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
        },
      });
      message.success('Override cleared');
      refetchRouting();
    } catch {
      message.error('Failed to clear override');
    }
  };

  // ============ Table Columns ============

  const platformColumns: ColumnsType<PlatformStats> = [
    {
      title: 'Источник',
      dataIndex: 'platform',
      key: 'platform',
      render: (platform: string, record: PlatformStats) => (
        <Tag color={getSourceColor(platform)}>
          {getSourceLabel(platform, record.bucket)}
        </Tag>
      ),
    },
    {
      title: 'Всего',
      dataIndex: 'total',
      key: 'total',
      sorter: (a, b) => a.total - b.total,
    },
    {
      title: '% успеха',
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
      title: <P95Tooltip><span>P95 Total</span></P95Tooltip>,
      dataIndex: 'p95_total_ms',
      key: 'p95_total_ms',
      render: formatMs,
      sorter: (a, b) => (a.p95_total_ms || 0) - (b.p95_total_ms || 0),
    },
    {
      title: <P95Tooltip><span>P95 Prep</span></P95Tooltip>,
      dataIndex: 'p95_prep_ms',
      key: 'p95_prep_ms',
      render: formatMs,
    },
    {
      title: <P95Tooltip><span>P95 Download</span></P95Tooltip>,
      dataIndex: 'p95_download_ms',
      key: 'p95_download_ms',
      render: formatMs,
    },
    {
      title: <P95Tooltip><span>P95 Upload</span></P95Tooltip>,
      dataIndex: 'p95_upload_ms',
      key: 'p95_upload_ms',
      render: formatMs,
    },
    {
      title: 'Скорость',
      dataIndex: 'avg_speed_kbps',
      key: 'avg_speed_kbps',
      render: formatSpeed,
    },
    {
      title: 'Провайдеры',
      dataIndex: 'provider_share',
      key: 'provider_share',
      render: (share: Record<string, number>) => (
        <div style={{ fontSize: '12px' }}>
          {Object.entries(share).map(([prov, pct]) => (
            <div key={prov}>
              <Tag color={
                prov === 'pytubefix' ? 'blue' :
                prov === 'rapidapi' ? 'green' :
                prov === 'ytdlp' ? 'purple' :
                prov === 'savenow' ? 'orange' : 'default'
              }>
                {prov}: {pct}%
              </Tag>
            </div>
          ))}
        </div>
      ),
    },
    {
      title: 'Ошибка',
      dataIndex: 'top_error_class',
      key: 'top_error_class',
      render: (err: string | null) => err ? (
        <Tooltip title={err}>
          <Tag color="error">{err.slice(0, 12)}</Tag>
        </Tooltip>
      ) : '-',
    },
  ];

  const providerColumns: ColumnsType<ProviderStats> = [
    {
      title: 'Провайдер',
      dataIndex: 'provider',
      key: 'provider',
      render: (provider: string, record: ProviderStats) => (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Tag color={
            provider === 'pytubefix' ? 'blue' :
            provider === 'rapidapi' ? 'green' :
            provider === 'ytdlp' ? 'purple' :
            provider === 'savenow' ? 'orange' : 'default'
          }>
            {provider.toUpperCase()}
          </Tag>
          {getHealthBadge(record.health)}
        </div>
      ),
    },
    {
      title: 'Вкл',
      dataIndex: 'enabled',
      key: 'enabled',
      width: 60,
      render: (enabled: boolean, record: ProviderStats) => (
        <Switch
          size="small"
          checked={enabled}
          onChange={(checked) => handleToggleProvider(record.provider, checked)}
        />
      ),
    },
    {
      title: 'Cooldown',
      dataIndex: 'cooldown_until',
      key: 'cooldown_until',
      width: 120,
      render: (cooldown: string | null, record: ProviderStats) => {
        if (cooldown) {
          const until = new Date(cooldown);
          const now = new Date();
          if (until > now) {
            const mins = Math.round((until.getTime() - now.getTime()) / 60000);
            return (
              <Tooltip title={`До ${until.toLocaleTimeString()}`}>
                <Tag color="orange" icon={<PauseCircleOutlined />}>
                  {mins}m
                </Tag>
              </Tooltip>
            );
          }
        }
        return (
          <Button
            size="small"
            onClick={() => handleCooldown(record.provider, 30)}
          >
            +30m
          </Button>
        );
      },
    },
    {
      title: 'Всего',
      dataIndex: 'total',
      key: 'total',
    },
    {
      title: '% успеха',
      dataIndex: 'success_rate',
      key: 'success_rate',
      render: (rate: number) => (
        <span style={{ color: getSuccessRateColor(rate) }}>
          {rate.toFixed(1)}%
        </span>
      ),
    },
    {
      title: <P95Tooltip><span>P95</span></P95Tooltip>,
      dataIndex: 'p95_total_ms',
      key: 'p95_total_ms',
      render: formatMs,
    },
    {
      title: 'Скорость',
      dataIndex: 'avg_speed_kbps',
      key: 'avg_speed_kbps',
      render: formatSpeed,
    },
    {
      title: 'CDN хосты',
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
      title: 'Последний успех',
      dataIndex: 'last_success_at',
      key: 'last_success_at',
      width: 100,
      render: (ts: string | null) => (
        <span style={{ color: ts ? '#52c41a' : '#888', fontSize: '12px' }}>
          {formatTimeAgo(ts)}
        </span>
      ),
    },
    {
      title: 'Последняя ошибка',
      dataIndex: 'last_error_at',
      key: 'last_error_at',
      width: 130,
      render: (_: string | null, record: ProviderStats) => (
        <div style={{ fontSize: '12px' }}>
          {record.last_error_at ? (
            <Tooltip title={record.last_error_class || 'Unknown'}>
              <span style={{ color: '#ff4d4f' }}>
                {formatTimeAgo(record.last_error_at)}
                {record.last_error_class && (
                  <Tag color="error" style={{ marginLeft: '4px', fontSize: '10px' }}>
                    {record.last_error_class.slice(0, 8)}
                  </Tag>
                )}
              </span>
            </Tooltip>
          ) : (
            <span style={{ color: '#52c41a' }}>Нет ошибок</span>
          )}
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
              { value: '1h', label: '1 час' },
              { value: '24h', label: '24 часа' },
              { value: '7d', label: '7 дней' },
            ]}
          />
          <Tooltip title="Автообновление: 30с">
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
              title="Общий % успеха"
              value={overallSuccessRate}
              precision={1}
              suffix="%"
              valueStyle={{ color: getSuccessRateColor(overallSuccessRate) }}
              prefix={overallSuccessRate >= 90 ? <CheckCircleOutlined /> : <WarningOutlined />}
            />
            <div style={{ fontSize: '12px', color: '#888', marginTop: '8px' }}>
              {totalSuccess} / {totalSuccess + totalErrors} загрузок
            </div>
          </Card>
        </Col>

        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Tooltip title="95% загрузок быстрее этого времени">
              <Statistic
                title="Худшая P95 задержка"
                value={worstP95 > 0 ? formatMs(worstP95) : '-'}
                valueStyle={{ color: worstP95 > 30000 ? '#ff4d4f' : worstP95 > 15000 ? '#faad14' : '#52c41a' }}
                prefix={<ClockCircleOutlined />}
              />
            </Tooltip>
            <div style={{ fontSize: '12px', color: '#888', marginTop: '8px' }}>
              По всем платформам
            </div>
          </Card>
        </Col>

        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Tooltip title="Instagram, TikTok, Pinterest - 1 скачивание = 1 запрос">
              <Statistic
                title="Квота IG/TT/Pin"
                value={socialUsedPercent !== null ? socialUsedPercent : '-'}
                suffix={socialUsedPercent !== null ? '% потрачено' : ''}
                valueStyle={{
                  color: socialUsedPercent !== null
                    ? (socialUsedPercent > 80 ? '#ff4d4f' : socialUsedPercent > 50 ? '#faad14' : '#52c41a')
                    : '#888'
                }}
                prefix={<DatabaseOutlined />}
              />
            </Tooltip>
            <div style={{ fontSize: '12px', color: '#888', marginTop: '8px' }}>
              {socialRemaining !== null && socialRemaining !== undefined && socialLimit
                ? `${socialRemaining.toLocaleString()} из ${socialLimit.toLocaleString()} шт`
                : 'Нет данных'
              }
            </div>
          </Card>
        </Col>

        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="Активные операции"
              value={`${(system?.active_downloads ?? 0)} / ${(system?.active_uploads ?? 0)}`}
              prefix={<ThunderboltOutlined />}
              valueStyle={{ color: '#1890ff', fontSize: '24px' }}
            />
            <div style={{ fontSize: '12px', color: '#888', marginTop: '8px' }}>
              <span style={{ color: (system?.active_downloads ?? 0) > 0 ? '#52c41a' : '#888' }}>
                {system?.active_downloads ?? 0} скачиваний
              </span>
              {' / '}
              <span style={{ color: (system?.active_uploads ?? 0) > 0 ? '#1890ff' : '#888' }}>
                {system?.active_uploads ?? 0} загрузок
              </span>
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
                <CloudServerOutlined /> Источники
              </span>
            ),
            children: (
              <Card
                title={
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span>Статистика по источникам</span>
                    <Segmented
                      size="small"
                      options={[
                        { label: 'По платформе', value: 'platform' },
                        { label: 'По типу', value: 'bucket' },
                      ]}
                      value={groupBy}
                      onChange={(val) => setGroupBy(val as 'platform' | 'bucket')}
                    />
                  </div>
                }
              >
                {platformsLoading ? (
                  <div style={{ textAlign: 'center', padding: '40px' }}><Spin /></div>
                ) : (
                  <Table
                    dataSource={platforms}
                    columns={platformColumns}
                    rowKey={(record) => `${record.platform}-${record.bucket || 'all'}`}
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
                <ApiOutlined /> Провайдеры
              </span>
            ),
            children: (
              <Card title="Статистика по провайдерам">
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
                <DatabaseOutlined /> Система
              </span>
            ),
            children: (
              <Row gutter={[16, 16]}>
                {/* System Metrics */}
                <Col xs={24} lg={12}>
                  <Card title="Системные метрики (Hostkey)">
                    {systemLoading ? (
                      <Spin />
                    ) : system && system.cpu_percent !== null ? (
                      <div>
                        <div style={{ marginBottom: '16px' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                            <span>CPU</span>
                            <span>{system.cpu_percent.toFixed(1)}%</span>
                          </div>
                          <Progress
                            percent={system.cpu_percent}
                            showInfo={false}
                            strokeColor={system.cpu_percent > 80 ? '#ff4d4f' : '#1890ff'}
                          />
                        </div>
                        <div style={{ marginBottom: '16px' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                            <span>RAM</span>
                            <span>
                              {system.ram_used_bytes !== null && system.ram_total_bytes !== null
                                ? `${formatBytes(system.ram_used_bytes)} / ${formatBytes(system.ram_total_bytes)}`
                                : system.ram_percent !== null ? `${system.ram_percent.toFixed(1)}%` : 'Нет данных'
                              }
                            </span>
                          </div>
                          <Progress
                            percent={system.ram_percent ?? 0}
                            showInfo={false}
                            strokeColor={system.ram_percent && system.ram_percent > 80 ? '#ff4d4f' : '#52c41a'}
                          />
                        </div>
                        <div style={{ marginBottom: '16px' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                            <span>Диск</span>
                            <span>
                              {system.disk_used_bytes !== null && system.disk_total_bytes !== null
                                ? `${formatBytes(system.disk_used_bytes)} / ${formatBytes(system.disk_total_bytes)}`
                                : system.disk_percent !== null ? `${system.disk_percent.toFixed(1)}%` : 'Нет данных'
                              }
                            </span>
                          </div>
                          <Progress
                            percent={system.disk_percent ?? 0}
                            showInfo={false}
                            strokeColor={system.disk_percent && system.disk_percent > 90 ? '#ff4d4f' : '#faad14'}
                          />
                        </div>
                        <div>
                          <span>/tmp размер: </span>
                          <strong>
                            {system.tmp_used_bytes !== null
                              ? formatBytes(system.tmp_used_bytes)
                              : 'Нет данных'
                            }
                          </strong>
                        </div>
                      </div>
                    ) : (
                      <div style={{ color: '#888', textAlign: 'center', padding: '20px' }}>
                        Нет данных с сервера Hostkey.
                        <br />
                        <span style={{ fontSize: '12px' }}>Метрики обновляются каждые 30 секунд</span>
                      </div>
                    )}
                  </Card>
                </Col>

                {/* Quota Info */}
                <Col xs={24} lg={12}>
                  <Card title="Квоты API">
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
                            {(() => {
                              // Выбираем правильные поля: units для savenow, requests для social_download
                              const remaining = quota.units_remaining ?? quota.requests_remaining;
                              const limit = quota.units_limit ?? quota.requests_limit;
                              const resetHours = quota.reset_hours;
                              const daysUntilReset = resetHours ? Math.ceil(resetHours / 24) : null;
                              const isSavenow = quota.provider === 'savenow';
                              const unitLabel = isSavenow ? 'токенов' : 'шт';

                              // Прогноз использования к концу месяца
                              const projectedUsage = quota.burn_rate_24h && daysUntilReset
                                ? Math.round(quota.burn_rate_24h * daysUntilReset)
                                : null;
                              const projectedPercent = projectedUsage && limit
                                ? Math.round((projectedUsage / limit) * 100)
                                : null;

                              return (
                                <Row gutter={[16, 8]}>
                                  <Col span={12}>
                                    <Tooltip title={isSavenow ? 'Токены (длинные видео = больше токенов)' : '1 скачивание = 1 запрос'}>
                                      <div style={{ fontSize: '12px', color: '#888' }}>
                                        Осталось {unitLabel}
                                      </div>
                                    </Tooltip>
                                    <div style={{ fontSize: '18px', fontWeight: 'bold' }}>
                                      {remaining !== null ? (
                                        <>
                                          {remaining.toLocaleString()}
                                          {limit && (
                                            <span style={{ fontSize: '12px', color: '#888' }}> / {limit.toLocaleString()}</span>
                                          )}
                                        </>
                                      ) : (
                                        <span style={{ fontSize: '14px', color: '#888' }}>Нет данных</span>
                                      )}
                                    </div>
                                  </Col>
                                  <Col span={12}>
                                    <Tooltip title={isSavenow
                                      ? "Потрачено токенов с начала месяца (из API)"
                                      : "Сколько скачиваний сделано за последние 24 часа"
                                    }>
                                      <div style={{ fontSize: '12px', color: '#888' }}>
                                        {isSavenow ? 'Потрачено за месяц' : 'Скачано за 24ч'}
                                      </div>
                                    </Tooltip>
                                    <div style={{ fontSize: '18px', fontWeight: 'bold' }}>
                                      {quota.burn_rate_24h !== null ? (
                                        <>{quota.burn_rate_24h} <span style={{ fontSize: '12px' }}>{isSavenow ? 'токенов' : 'шт'}</span></>
                                      ) : (
                                        <span style={{ fontSize: '14px', color: '#888' }}>-</span>
                                      )}
                                    </div>
                                  </Col>
                                  <Col span={12}>
                                    <Tooltip title="Когда квота обнулится и начнётся новый месяц">
                                      <div style={{ fontSize: '12px', color: '#888' }}>Новый месяц через</div>
                                    </Tooltip>
                                    <div style={{ fontSize: '18px', fontWeight: 'bold' }}>
                                      {daysUntilReset !== null ? (
                                        <>{daysUntilReset} <span style={{ fontSize: '12px' }}>дней</span></>
                                      ) : (
                                        <span style={{ fontSize: '14px', color: '#888' }}>-</span>
                                      )}
                                    </div>
                                  </Col>
                                  <Col span={12}>
                                    <Tooltip title={isSavenow
                                      ? "Сколько % квоты уже использовано"
                                      : "Сколько % квоты потратим к концу месяца при текущем темпе"
                                    }>
                                      <div style={{ fontSize: '12px', color: '#888' }}>
                                        {isSavenow ? 'Использовано' : 'Прогноз на месяц'}
                                      </div>
                                    </Tooltip>
                                    <div style={{
                                      fontSize: '18px',
                                      fontWeight: 'bold',
                                      color: (isSavenow ? quota.forecast_average : projectedPercent) !== null
                                        ? ((isSavenow ? quota.forecast_average : projectedPercent) as number > 90 ? '#ff4d4f' :
                                           (isSavenow ? quota.forecast_average : projectedPercent) as number > 70 ? '#faad14' : '#52c41a')
                                        : '#888'
                                    }}>
                                      {(isSavenow ? quota.forecast_average : projectedPercent) !== null ? (
                                        <>{isSavenow ? quota.forecast_average : projectedPercent}%</>
                                      ) : (
                                        <span style={{ fontSize: '14px', color: '#888' }}>-</span>
                                      )}
                                    </div>
                                  </Col>
                                </Row>
                              );
                            })()}
                            {(() => {
                              const remaining = quota.units_remaining ?? quota.requests_remaining;
                              const limit = quota.units_limit ?? quota.requests_limit;
                              if (remaining === null || !limit) return null;
                              const percent = Math.round((remaining / limit) * 100);
                              return (
                                <Progress
                                  percent={percent}
                                  strokeColor={{
                                    '0%': '#ff4d4f',
                                    '50%': '#faad14',
                                    '100%': '#52c41a',
                                  }}
                                  style={{ marginTop: '12px' }}
                                  format={() => `${percent}% осталось`}
                                />
                              );
                            })()}
                          </Card>
                        ))}
                      </div>
                    ) : (
                      <div style={{ color: '#888' }}>Нет данных о квотах</div>
                    )}
                  </Card>
                </Col>
              </Row>
            ),
          },
          {
            key: 'routing',
            label: (
              <span>
                <BranchesOutlined /> Routing
              </span>
            ),
            children: (
              <Card
                title="Настройка маршрутизации провайдеров"
                style={{ backgroundColor: '#1f1f1f', borderColor: '#303030' }}
                styles={{ header: { borderColor: '#303030' } }}
              >
                {routingLoading ? (
                  <div style={{ textAlign: 'center', padding: '40px' }}><Spin /></div>
                ) : (
                  <Row gutter={[24, 24]}>
                    {/* Source selector */}
                    <Col span={24}>
                      <div style={{ marginBottom: '16px' }}>
                        <span style={{ marginRight: '12px', fontWeight: 'bold' }}>Источник:</span>
                        <Select
                          value={selectedSource}
                          onChange={(val) => {
                            setSelectedSource(val);
                            setEditedChain(null);
                          }}
                          style={{ width: 200 }}
                          dropdownStyle={{ backgroundColor: '#1f1f1f', borderColor: '#303030' }}
                          options={routingSources.map(r => ({
                            value: r.source,
                            label: SOURCE_LABELS[r.source] || r.source,
                          }))}
                        />
                        {currentRouting?.has_override && (
                          <Tag color="orange" style={{ marginLeft: '12px' }}>
                            Override активен до {new Date(currentRouting.override_expires_at!).toLocaleTimeString()}
                            <Button
                              type="link"
                              size="small"
                              onClick={handleClearOverride}
                              style={{ padding: '0 4px' }}
                            >
                              Снять
                            </Button>
                          </Tag>
                        )}
                      </div>
                    </Col>

                    {/* Chain editor */}
                    <Col xs={24} lg={12}>
                      <Card
                        size="small"
                        title="Порядок провайдеров"
                        style={{ backgroundColor: '#141414', borderColor: '#303030' }}
                        styles={{ header: { borderColor: '#303030' } }}
                        extra={
                          <div>
                            {editedChain && (
                              <>
                                <Button
                                  type="primary"
                                  size="small"
                                  icon={<SaveOutlined />}
                                  onClick={handleSaveRouting}
                                  loading={routingSaving}
                                  style={{ marginRight: '8px' }}
                                >
                                  Сохранить
                                </Button>
                                <Button
                                  size="small"
                                  onClick={() => setEditedChain(null)}
                                >
                                  Отмена
                                </Button>
                              </>
                            )}
                            {!editedChain && (
                              <Button
                                size="small"
                                icon={<UndoOutlined />}
                                onClick={handleResetRouting}
                                loading={routingSaving}
                              >
                                Сбросить
                              </Button>
                            )}
                          </div>
                        }
                      >
                        {displayChain.map((provider, index) => (
                          <div
                            key={provider.name}
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              padding: '10px 14px',
                              marginBottom: '8px',
                              backgroundColor: provider.enabled ? '#1a1a2e' : '#16213e',
                              borderRadius: '6px',
                              border: `1px solid ${provider.enabled ? '#0f3460' : '#1a1a2e'}`,
                              opacity: provider.enabled ? 1 : 0.7,
                            }}
                          >
                            <span style={{ marginRight: '12px', color: '#94a3b8', minWidth: '24px', fontWeight: 'bold' }}>
                              {index + 1}.
                            </span>
                            <Tag color={PROVIDER_COLORS[provider.name] || 'default'} style={{ fontSize: '13px' }}>
                              {PROVIDER_LABELS[provider.name] || provider.name}
                            </Tag>
                            <div style={{ flex: 1 }} />
                            <Switch
                              size="small"
                              checked={provider.enabled}
                              onChange={() => handleToggleProviderInChain(index)}
                              style={{ marginRight: '8px' }}
                            />
                            <Button
                              type="text"
                              size="small"
                              icon={<ArrowUpOutlined />}
                              disabled={index === 0}
                              onClick={() => handleMoveProvider(index, 'up')}
                            />
                            <Button
                              type="text"
                              size="small"
                              icon={<ArrowDownOutlined />}
                              disabled={index === displayChain.length - 1}
                              onClick={() => handleMoveProvider(index, 'down')}
                            />
                          </div>
                        ))}
                        {displayChain.length === 0 && (
                          <div style={{ color: '#888', textAlign: 'center', padding: '20px' }}>
                            Нет провайдеров
                          </div>
                        )}
                      </Card>
                    </Col>

                    {/* Info */}
                    <Col xs={24} lg={12}>
                      <Card
                        size="small"
                        title="Как это работает"
                        style={{ backgroundColor: '#141414', borderColor: '#303030' }}
                        styles={{ header: { borderColor: '#303030' }, body: { color: '#d9d9d9' } }}
                      >
                        <ul style={{ paddingLeft: '20px', margin: 0, color: '#d9d9d9' }}>
                          <li>Бот пробует провайдеров <b>сверху вниз</b></li>
                          <li>Если первый упал — пробует второго, и т.д.</li>
                          <li>Выключенные провайдеры пропускаются</li>
                          <li>Изменения применяются <b>мгновенно</b></li>
                        </ul>
                        <div style={{ marginTop: '16px', padding: '12px', backgroundColor: 'rgba(82, 196, 26, 0.1)', borderRadius: '4px', border: '1px solid rgba(82, 196, 26, 0.3)', color: '#d9d9d9' }}>
                          <b style={{ color: '#52c41a' }}>Совет:</b> Если YouTube банит — поставь SaveNow первым.
                        </div>
                      </Card>
                    </Col>
                  </Row>
                )}
              </Card>
            ),
          },
        ]}
      />
    </div>
  );
};
