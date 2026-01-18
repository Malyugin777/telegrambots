import { List, useTable, TagField } from '@refinedev/antd';
import { useCustom } from '@refinedev/core';
import { Table, Card, Row, Col, Statistic, Select, Space, Button } from 'antd';
import { ReloadOutlined, WarningOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { useState } from 'react';

interface DownloadError {
  id: number;
  user_id: number | null;
  bot_id: number | null;
  platform: string;
  url: string;
  error_type: string;
  error_message: string | null;
  error_details: Record<string, unknown> | null;
  created_at: string;
}

interface ErrorStats {
  total_errors: number;
  errors_today: number;
  errors_by_platform: Record<string, number>;
  errors_by_type: Record<string, number>;
}

const platformColors: Record<string, string> = {
  instagram: 'magenta',
  tiktok: 'cyan',
  youtube: 'red',
  pinterest: 'volcano',
  unknown: 'default',
};

const errorTypeColors: Record<string, string> = {
  download_failed: 'orange',
  exception: 'red',
  timeout: 'gold',
  network: 'blue',
};

export const ErrorList = () => {
  const [platformFilter, setPlatformFilter] = useState<string | undefined>();
  const [typeFilter, setTypeFilter] = useState<string | undefined>();

  const { tableProps, tableQueryResult } = useTable<DownloadError>({
    resource: 'errors',
    syncWithLocation: true,
    filters: {
      permanent: [
        ...(platformFilter ? [{ field: 'platform', operator: 'eq' as const, value: platformFilter }] : []),
        ...(typeFilter ? [{ field: 'error_type', operator: 'eq' as const, value: typeFilter }] : []),
      ],
    },
  });

  const { data: statsData } = useCustom<ErrorStats>({
    url: '/errors/stats',
    method: 'get',
  });

  const stats = statsData?.data;

  return (
    <List
      title="Ошибки скачивания"
      headerButtons={
        <Button icon={<ReloadOutlined />} onClick={() => tableQueryResult.refetch()}>
          Обновить
        </Button>
      }
    >
      {/* Stats Cards */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="Всего ошибок"
              value={stats?.total_errors || 0}
              prefix={<WarningOutlined />}
              valueStyle={{ color: '#ff4d4f' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="Сегодня"
              value={stats?.errors_today || 0}
              valueStyle={{ color: '#faad14' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="Instagram"
              value={stats?.errors_by_platform?.instagram || 0}
              valueStyle={{ color: '#eb2f96' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="TikTok"
              value={stats?.errors_by_platform?.tiktok || 0}
              valueStyle={{ color: '#13c2c2' }}
            />
          </Card>
        </Col>
      </Row>

      {/* Filters */}
      <Space style={{ marginBottom: 16 }}>
        <Select
          placeholder="Платформа"
          style={{ width: 150 }}
          allowClear
          value={platformFilter}
          onChange={setPlatformFilter}
          options={[
            { label: 'Instagram', value: 'instagram' },
            { label: 'TikTok', value: 'tiktok' },
            { label: 'YouTube', value: 'youtube' },
            { label: 'Pinterest', value: 'pinterest' },
          ]}
        />
        <Select
          placeholder="Тип ошибки"
          style={{ width: 150 }}
          allowClear
          value={typeFilter}
          onChange={setTypeFilter}
          options={[
            { label: 'Download Failed', value: 'download_failed' },
            { label: 'Exception', value: 'exception' },
            { label: 'Timeout', value: 'timeout' },
          ]}
        />
      </Space>

      <Table {...tableProps} rowKey="id" scroll={{ x: true }}>
        <Table.Column dataIndex="id" title="ID" width={60} />
        <Table.Column
          dataIndex="platform"
          title="Платформа"
          width={100}
          render={(value: string) => (
            <TagField color={platformColors[value] || 'default'} value={value} />
          )}
        />
        <Table.Column
          dataIndex="error_type"
          title="Тип"
          width={120}
          render={(value: string) => (
            <TagField color={errorTypeColors[value] || 'default'} value={value} />
          )}
        />
        <Table.Column
          dataIndex="error_message"
          title="Сообщение"
          ellipsis
          render={(value: string | null) => value || '-'}
        />
        <Table.Column
          dataIndex="url"
          title="URL"
          width={200}
          ellipsis
          render={(value: string) => (
            <a href={value} target="_blank" rel="noopener noreferrer">
              {value.substring(0, 40)}...
            </a>
          )}
        />
        <Table.Column
          dataIndex="created_at"
          title="Время"
          width={130}
          render={(value: string) => dayjs(value).format('DD.MM.YY HH:mm')}
        />
      </Table>
    </List>
  );
};
