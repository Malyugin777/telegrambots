import { useLogin } from '@refinedev/core';
import { Form, Input, Button, Card, Typography, message, Space } from 'antd';
import { UserOutlined, LockOutlined, RobotOutlined } from '@ant-design/icons';
import { useState } from 'react';
import axios from 'axios';

const { Title, Text, Link } = Typography;

interface LoginForm {
  username: string;
  password: string;
}

export const Login = () => {
  const { mutate: login, isLoading } = useLogin<LoginForm>();
  const [setupMode, setSetupMode] = useState(false);
  const [setupLoading, setSetupLoading] = useState(false);

  const onFinish = (values: LoginForm) => {
    login(values, {
      onError: () => {
        message.error('Invalid credentials');
      },
    });
  };

  const onSetup = async (values: LoginForm & { email: string }) => {
    setSetupLoading(true);
    try {
      await axios.post('/api/v1/auth/setup', values);
      message.success('Admin user created! You can now login.');
      setSetupMode(false);
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || 'Setup failed');
    } finally {
      setSetupLoading(false);
    }
  };

  return (
    <div
      style={{
        height: '100vh',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        background: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)',
      }}
    >
      <Card
        style={{
          width: 400,
          boxShadow: '0 4px 20px rgba(0, 0, 0, 0.3)',
        }}
      >
        <Space direction="vertical" style={{ width: '100%', textAlign: 'center' }}>
          <RobotOutlined style={{ fontSize: 48, color: '#1890ff' }} />
          <Title level={2} style={{ margin: 0 }}>
            Nexus Control
          </Title>
          <Text type="secondary">Bot Network Admin Panel</Text>
        </Space>

        {!setupMode ? (
          <Form
            name="login"
            onFinish={onFinish}
            layout="vertical"
            style={{ marginTop: 24 }}
          >
            <Form.Item
              name="username"
              rules={[{ required: true, message: 'Please enter username' }]}
            >
              <Input
                prefix={<UserOutlined />}
                placeholder="Username"
                size="large"
              />
            </Form.Item>

            <Form.Item
              name="password"
              rules={[{ required: true, message: 'Please enter password' }]}
            >
              <Input.Password
                prefix={<LockOutlined />}
                placeholder="Password"
                size="large"
              />
            </Form.Item>

            <Form.Item>
              <Button
                type="primary"
                htmlType="submit"
                size="large"
                block
                loading={isLoading}
              >
                Sign In
              </Button>
            </Form.Item>

            <div style={{ textAlign: 'center' }}>
              <Link onClick={() => setSetupMode(true)}>
                First time? Create admin account
              </Link>
            </div>
          </Form>
        ) : (
          <Form
            name="setup"
            onFinish={onSetup}
            layout="vertical"
            style={{ marginTop: 24 }}
          >
            <Title level={5}>Initial Setup</Title>
            <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
              Create the first admin account
            </Text>

            <Form.Item
              name="username"
              rules={[
                { required: true, message: 'Please enter username' },
                { min: 3, message: 'At least 3 characters' },
              ]}
            >
              <Input
                prefix={<UserOutlined />}
                placeholder="Username"
                size="large"
              />
            </Form.Item>

            <Form.Item
              name="email"
              rules={[
                { required: true, message: 'Please enter email' },
                { type: 'email', message: 'Invalid email' },
              ]}
            >
              <Input
                prefix={<UserOutlined />}
                placeholder="Email"
                size="large"
              />
            </Form.Item>

            <Form.Item
              name="password"
              rules={[
                { required: true, message: 'Please enter password' },
                { min: 8, message: 'At least 8 characters' },
              ]}
            >
              <Input.Password
                prefix={<LockOutlined />}
                placeholder="Password"
                size="large"
              />
            </Form.Item>

            <Form.Item>
              <Button
                type="primary"
                htmlType="submit"
                size="large"
                block
                loading={setupLoading}
              >
                Create Admin Account
              </Button>
            </Form.Item>

            <div style={{ textAlign: 'center' }}>
              <Link onClick={() => setSetupMode(false)}>
                Back to login
              </Link>
            </div>
          </Form>
        )}
      </Card>
    </div>
  );
};
