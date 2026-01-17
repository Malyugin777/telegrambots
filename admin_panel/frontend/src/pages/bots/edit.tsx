import { Edit, useForm } from '@refinedev/antd';
import { Form, Input, Select } from 'antd';

export const BotEdit = () => {
  const { formProps, saveButtonProps, queryResult } = useForm();

  return (
    <Edit saveButtonProps={saveButtonProps}>
      <Form {...formProps} layout="vertical">
        <Form.Item
          label="Bot Name"
          name="name"
          rules={[{ required: true, message: 'Please enter bot name' }]}
        >
          <Input placeholder="My Awesome Bot" />
        </Form.Item>

        <Form.Item
          label="New Bot Token"
          name="token"
          extra="Leave empty to keep current token"
        >
          <Input.Password placeholder="Enter new token to update" />
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

        <Form.Item label="Status" name="status">
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
    </Edit>
  );
};
