import {
  List,
  useTable,
  EditButton,
  ShowButton,
  DeleteButton,
  TagField,
} from '@refinedev/antd';
import { Table, Space, Select, Button, Progress } from 'antd';
import {
  PlayCircleOutlined,
  StopOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { useCustom } from '@refinedev/core';
import { useState } from 'react';
import dayjs from 'dayjs';

interface Broadcast {
  id: number;
  name: string;
  text: string;
  status: 'draft' | 'scheduled' | 'running' | 'completed' | 'cancelled';
  total_recipients: number;
  sent_count: number;
  failed_count: number;
  scheduled_at: string | null;
  created_at: string;
}

const statusColors: Record<string, string> = {
  draft: 'default',
  scheduled: 'blue',
  running: 'processing',
  completed: 'green',
  cancelled: 'red',
};

export const BroadcastList = () => {
  const [statusFilter, setStatusFilter] = useState<string | undefined>();

  const { tableProps, tableQueryResult } = useTable<Broadcast>({
    resource: 'broadcasts',
    syncWithLocation: true,
    filters: {
      permanent: statusFilter
        ? [{ field: 'status_filter', operator: 'eq' as const, value: statusFilter }]
        : [],
    },
  });

  return (
    <List>
      {/* Filters */}
      <Space style={{ marginBottom: 16 }}>
        <Select
          placeholder="Status"
          style={{ width: 150 }}
          allowClear
          value={statusFilter}
          onChange={setStatusFilter}
          options={[
            { label: 'Draft', value: 'draft' },
            { label: 'Scheduled', value: 'scheduled' },
            { label: 'Running', value: 'running' },
            { label: 'Completed', value: 'completed' },
            { label: 'Cancelled', value: 'cancelled' },
          ]}
        />
        <Button
          icon={<ReloadOutlined />}
          onClick={() => tableQueryResult.refetch()}
        >
          Refresh
        </Button>
      </Space>

      <Table {...tableProps} rowKey="id">
        <Table.Column dataIndex="id" title="ID" width={80} />
        <Table.Column dataIndex="name" title="Name" />
        <Table.Column
          dataIndex="text"
          title="Text"
          render={(value: string) =>
            value.length > 50 ? value.substring(0, 50) + '...' : value
          }
        />
        <Table.Column
          dataIndex="status"
          title="Status"
          render={(value: string) => (
            <TagField color={statusColors[value] || 'default'} value={value.toUpperCase()} />
          )}
        />
        <Table.Column
          title="Progress"
          render={(_, record: Broadcast) => {
            if (record.total_recipients === 0) return '-';
            const percent = Math.round(
              ((record.sent_count + record.failed_count) / record.total_recipients) * 100
            );
            return (
              <Progress
                percent={percent}
                size="small"
                status={record.failed_count > 0 ? 'exception' : undefined}
              />
            );
          }}
        />
        <Table.Column
          dataIndex="scheduled_at"
          title="Scheduled"
          render={(value) =>
            value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '-'
          }
        />
        <Table.Column
          title="Actions"
          render={(_, record: Broadcast) => (
            <Space>
              <ShowButton hideText size="small" recordItemId={record.id} />
              {record.status === 'draft' && (
                <>
                  <EditButton hideText size="small" recordItemId={record.id} />
                  <Button
                    size="small"
                    type="primary"
                    icon={<PlayCircleOutlined />}
                    title="Start"
                  />
                  <DeleteButton hideText size="small" recordItemId={record.id} />
                </>
              )}
              {record.status === 'running' && (
                <Button
                  size="small"
                  danger
                  icon={<StopOutlined />}
                  title="Cancel"
                />
              )}
            </Space>
          )}
        />
      </Table>
    </List>
  );
};
