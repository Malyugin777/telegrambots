import { Create, useForm } from '@refinedev/antd';
import { Form, Input, InputNumber, Select, DatePicker, Switch, Space, Card } from 'antd';
import dayjs from 'dayjs';

export const SubscriptionCreate = () => {
  const { formProps, saveButtonProps } = useForm({
    resource: 'subscriptions',
    action: 'create',
  });

  return (
    <Create saveButtonProps={saveButtonProps}>
      <Form
        {...formProps}
        layout="vertical"
        initialValues={{
          provider: 'other',
          currency: 'RUB',
          billing_cycle: 'monthly',
          auto_renew: true,
          notify_days: [7, 3, 1],
          status: 'active',
          amount: 0,
        }}
      >
        <Card title="Основная информация" style={{ marginBottom: 16 }}>
          <Form.Item
            label="Название"
            name="name"
            rules={[{ required: true, message: 'Введите название' }]}
          >
            <Input placeholder="Aeza VPS #1" />
          </Form.Item>

          <Form.Item
            label="Описание"
            name="description"
          >
            <Input.TextArea rows={2} placeholder="API сервер, 185.96.80.254" />
          </Form.Item>

          <Space size="large">
            <Form.Item
              label="Провайдер"
              name="provider"
              rules={[{ required: true }]}
            >
              <Select style={{ width: 200 }}>
                <Select.Option value="aeza">Aeza VPS</Select.Option>
                <Select.Option value="hostkey">Hostkey VPS</Select.Option>
                <Select.Option value="rapidapi">RapidAPI</Select.Option>
                <Select.Option value="domain">Домен</Select.Option>
                <Select.Option value="github">GitHub</Select.Option>
                <Select.Option value="other">Другое</Select.Option>
              </Select>
            </Form.Item>

            <Form.Item
              label="Ссылка на ЛК"
              name="provider_url"
            >
              <Input placeholder="https://my.aeza.net" style={{ width: 300 }} />
            </Form.Item>
          </Space>
        </Card>

        <Card title="Оплата" style={{ marginBottom: 16 }}>
          <Space size="large">
            <Form.Item
              label="Сумма"
              name="amount"
              rules={[{ required: true }]}
            >
              <InputNumber min={0} style={{ width: 150 }} />
            </Form.Item>

            <Form.Item
              label="Валюта"
              name="currency"
              rules={[{ required: true }]}
            >
              <Select style={{ width: 100 }}>
                <Select.Option value="RUB">RUB ₽</Select.Option>
                <Select.Option value="USD">USD $</Select.Option>
                <Select.Option value="EUR">EUR €</Select.Option>
              </Select>
            </Form.Item>

            <Form.Item
              label="Период"
              name="billing_cycle"
              rules={[{ required: true }]}
            >
              <Select style={{ width: 180 }}>
                <Select.Option value="monthly">Ежемесячно</Select.Option>
                <Select.Option value="yearly">Ежегодно</Select.Option>
                <Select.Option value="usage">По использованию</Select.Option>
              </Select>
            </Form.Item>
          </Space>

          <Form.Item
            label="Следующий платёж"
            name="next_payment_date"
            getValueProps={(value) => ({
              value: value ? dayjs(value) : null,
            })}
            getValueFromEvent={(date) => date?.toISOString()}
          >
            <DatePicker format="DD.MM.YYYY" style={{ width: 200 }} />
          </Form.Item>
        </Card>

        <Card title="Настройки">
          <Space size="large">
            <Form.Item
              label="Автопродление"
              name="auto_renew"
              valuePropName="checked"
            >
              <Switch checkedChildren="Да" unCheckedChildren="Нет" />
            </Form.Item>

            <Form.Item
              label="Статус"
              name="status"
              rules={[{ required: true }]}
            >
              <Select style={{ width: 150 }}>
                <Select.Option value="active">Активна</Select.Option>
                <Select.Option value="cancelled">Отменена</Select.Option>
                <Select.Option value="expired">Истекла</Select.Option>
              </Select>
            </Form.Item>

            <Form.Item
              label="Напоминать за (дней)"
              name="notify_days"
            >
              <Select
                mode="multiple"
                style={{ width: 200 }}
                options={[
                  { label: '1 день', value: 1 },
                  { label: '3 дня', value: 3 },
                  { label: '7 дней', value: 7 },
                  { label: '14 дней', value: 14 },
                  { label: '30 дней', value: 30 },
                ]}
              />
            </Form.Item>
          </Space>
        </Card>
      </Form>
    </Create>
  );
};
