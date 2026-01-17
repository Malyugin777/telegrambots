import { Create, useForm } from '@refinedev/antd';
import { Form, Input, Select } from 'antd';

export const BotCreate = () => {
  const { formProps, saveButtonProps } = useForm();

  return (
    <Create saveButtonProps={saveButtonProps}>
      <Form {...formProps} layout="vertical">
        <Form.Item
          label="Bot Name"
          name="name"
          rules={[{ required: true, message: 'Please enter bot name' }]}
        >
          <Input placeholder="My Awesome Bot" />
        </Form.Item>

        <Form.Item
          label="Bot Token"
          name="token"
          rules={[
            { required: true, message: 'Please enter bot token' },
            { min: 40, message: 'Token seems too short' },
          ]}
          extra="Get token from @BotFather on Telegram"
        >
          <Input.Password placeholder="123456789:ABCdefGHIjklMNOpqrSTUvwxYZ" />
        </Form.Item>

        <Form.Item
          label="Bot Username"
          name="bot_username"
          extra="Without @ symbol"
        >
          <Input placeholder="my_awesome_bot" />
        </Form.Item>

        <Form.Item label="Description" name="description">
          <Input.TextArea rows={3} placeholder="What does this bot do?" />
        </Form.Item>

        <Form.Item label="Webhook URL" name="webhook_url">
          <Input placeholder="https://your-domain.com/webhook/bot123" />
        </Form.Item>

        <Form.Item
          label="Status"
          name="status"
          initialValue="active"
        >
          <Select
            options={[
              { label: 'Active', value: 'active' },
              { label: 'Paused', value: 'paused' },
              { label: 'Maintenance', value: 'maintenance' },
              { label: 'Disabled', value: 'disabled' },
            ]}
          />
        </Form.Item>
      </Form>
    </Create>
  );
};
