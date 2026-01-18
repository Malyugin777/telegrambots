import {
  List,
  useTable,
  EditButton,
  DeleteButton,
  CreateButton,
  TagField,
} from '@refinedev/antd';
import { Table, Space, Select, Button, Card, Row, Col, Statistic, Tooltip } from 'antd';
import {
  ReloadOutlined,
  DollarOutlined,
  CalendarOutlined,
  LinkOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import { useState } from 'react';
import dayjs from 'dayjs';

interface Subscription {
  id: number;
  name: string;
  description: string | null;
  provider: 'aeza' | 'hostkey' | 'rapidapi' | 'domain' | 'github' | 'other';
  provider_url: string | null;
  amount: number;
  currency: string;
  billing_cycle: 'monthly' | 'yearly' | 'usage';
  next_payment_date: string | null;
  auto_renew: boolean;
  notify_days: number[];
  status: 'active' | 'cancelled' | 'expired';
  created_at: string;
  updated_at: string;
  days_until_payment: number | null;
}

const statusColors: Record<string, string> = {
  active: 'green',
  cancelled: 'orange',
  expired: 'red',
};

const providerColors: Record<string, string> = {
  aeza: '#00a86b',
  hostkey: '#1890ff',
  rapidapi: '#0055ff',
  domain: '#722ed1',
  github: '#24292e',
  other: 'default',
};

const providerLabels: Record<string, string> = {
  aeza: 'Aeza VPS',
  hostkey: 'Hostkey VPS',
  rapidapi: 'RapidAPI',
  domain: 'Домен',
  github: 'GitHub',
  other: 'Другое',
};

const cycleLabels: Record<string, string> = {
  monthly: 'Ежемесячно',
  yearly: 'Ежегодно',
  usage: 'По использованию',
};

export const SubscriptionList = () => {
  const [statusFilter, setStatusFilter] = useState<string | undefined>();

  const { tableProps, tableQueryResult } = useTable<Subscription>({
    resource: 'subscriptions',
    syncWithLocation: true,
    filters: {
      permanent: [
        ...(statusFilter ? [{ field: 'status_filter', operator: 'eq' as const, value: statusFilter }] : []),
      ],
    },
  });

  // Calculate totals
  const data = tableQueryResult.data?.data || [];
  const activeSubscriptions = data.filter((s: Subscription) => s.status === 'active');
  const monthlyTotal = activeSubscriptions
    .filter((s: Subscription) => s.billing_cycle === 'monthly')
    .reduce((sum: number, s: Subscription) => sum + (s.currency === 'RUB' ? s.amount : s.amount * 90), 0);
  const upcomingPayments = activeSubscriptions.filter(
    (s: Subscription) => s.days_until_payment !== null && s.days_until_payment <= 7
  );

  return (
    <List
      headerButtons={({ createButtonProps }) => (
        <Space>
          <Button
            icon={<ReloadOutlined />}
            onClick={() => tableQueryResult.refetch()}
          >
            Обновить
          </Button>
          <CreateButton {...createButtonProps} />
        </Space>
      )}
    >
      {/* Stats Cards */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="Активных подписок"
              value={activeSubscriptions.length}
              prefix={<ClockCircleOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="Ежемесячно (RUB)"
              value={monthlyTotal}
              prefix={<DollarOutlined />}
              precision={0}
              suffix="₽"
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="Платежей на неделе"
              value={upcomingPayments.length}
              prefix={<CalendarOutlined />}
              valueStyle={{ color: upcomingPayments.length > 0 ? '#faad14' : undefined }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="Всего подписок"
              value={data.length}
            />
          </Card>
        </Col>
      </Row>

      {/* Filters */}
      <Space style={{ marginBottom: 16 }}>
        <Select
          placeholder="Статус"
          style={{ width: 150 }}
          allowClear
          value={statusFilter}
          onChange={setStatusFilter}
          options={[
            { label: 'Активные', value: 'active' },
            { label: 'Отменённые', value: 'cancelled' },
            { label: 'Истекшие', value: 'expired' },
          ]}
        />
      </Space>

      <Table {...tableProps} rowKey="id">
        <Table.Column
          dataIndex="name"
          title="Название"
          render={(value: string, record: Subscription) => (
            <Space direction="vertical" size={0}>
              <strong>{value}</strong>
              {record.description && (
                <span style={{ fontSize: 12, color: '#888' }}>{record.description}</span>
              )}
            </Space>
          )}
        />
        <Table.Column
          dataIndex="provider"
          title="Провайдер"
          render={(value: string, record: Subscription) => (
            <Space>
              <TagField color={providerColors[value] || 'default'} value={providerLabels[value] || value} />
              {record.provider_url && (
                <Tooltip title="Открыть ЛК">
                  <a href={record.provider_url} target="_blank" rel="noopener noreferrer">
                    <LinkOutlined />
                  </a>
                </Tooltip>
              )}
            </Space>
          )}
        />
        <Table.Column
          dataIndex="amount"
          title="Стоимость"
          render={(value: number, record: Subscription) => (
            <span style={{ fontWeight: 500 }}>
              {value.toLocaleString()} {record.currency === 'RUB' ? '₽' : record.currency}
              <span style={{ fontSize: 12, color: '#888', marginLeft: 4 }}>
                / {cycleLabels[record.billing_cycle] || record.billing_cycle}
              </span>
            </span>
          )}
        />
        <Table.Column
          dataIndex="next_payment_date"
          title="Следующий платёж"
          render={(value: string | null, record: Subscription) => {
            if (!value) return <span style={{ color: '#888' }}>—</span>;

            const days = record.days_until_payment;
            let color = undefined;
            if (days !== null) {
              if (days <= 1) color = '#ff4d4f';
              else if (days <= 3) color = '#faad14';
              else if (days <= 7) color = '#1890ff';
            }

            return (
              <Space direction="vertical" size={0}>
                <span>{dayjs(value).format('DD.MM.YYYY')}</span>
                {days !== null && (
                  <span style={{ fontSize: 12, color: color || '#888' }}>
                    {days === 0 ? 'Сегодня!' : days === 1 ? 'Завтра' : `через ${days} дн.`}
                  </span>
                )}
              </Space>
            );
          }}
        />
        <Table.Column
          dataIndex="auto_renew"
          title="Автопродление"
          render={(value: boolean) => (
            <TagField
              color={value ? 'green' : 'default'}
              value={value ? 'Да' : 'Нет'}
            />
          )}
        />
        <Table.Column
          dataIndex="status"
          title="Статус"
          render={(value: string) => (
            <TagField
              color={statusColors[value] || 'default'}
              value={value === 'active' ? 'Активна' : value === 'cancelled' ? 'Отменена' : 'Истекла'}
            />
          )}
        />
        <Table.Column
          title="Действия"
          render={(_, record: Subscription) => (
            <Space>
              <EditButton hideText size="small" recordItemId={record.id} />
              <DeleteButton hideText size="small" recordItemId={record.id} />
            </Space>
          )}
        />
      </Table>
    </List>
  );
};
