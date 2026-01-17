import { useLogin } from '@refinedev/core';
import { Form, Input, Button, Card, Typography, message, Space } from 'antd';
import { UserOutlined, LockOutlined, RobotOutlined } from '@ant-design/icons';
import { useState } from 'react';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { LanguageSwitcher } from '../../components';

const { Title, Text, Link } = Typography;

interface LoginForm {
  username: string;
  password: string;
}

export const Login = () => {
  const { t } = useTranslation();
  const { mutate: login, isLoading } = useLogin<LoginForm>();
  const [setupMode, setSetupMode] = useState(false);
  const [setupLoading, setSetupLoading] = useState(false);

  const onFinish = (values: LoginForm) => {
    login(values, {
      onError: () => {
        message.error(t('auth.invalidCredentials'));
      },
    });
  };

  const onSetup = async (values: LoginForm & { email: string }) => {
    setSetupLoading(true);
    try {
      await axios.post('/api/v1/auth/setup', values);
      message.success(t('auth.adminCreated'));
      setSetupMode(false);
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || t('auth.setupFailed'));
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
        position: 'relative',
      }}
    >
      {/* Language Switcher */}
      <div style={{ position: 'absolute', top: 16, right: 16 }}>
        <LanguageSwitcher />
      </div>

      <Card
        style={{
          width: 400,
          boxShadow: '0 4px 20px rgba(0, 0, 0, 0.3)',
        }}
      >
        <Space direction="vertical" style={{ width: '100%', textAlign: 'center' }}>
          <RobotOutlined style={{ fontSize: 48, color: '#1890ff' }} />
          <Title level={2} style={{ margin: 0 }}>
            {t('common.appName')}
          </Title>
          <Text type="secondary">{t('common.appSubtitle')}</Text>
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
              rules={[{ required: true, message: t('auth.validation.usernameRequired') }]}
            >
              <Input
                prefix={<UserOutlined />}
                placeholder={t('auth.username')}
                size="large"
              />
            </Form.Item>

            <Form.Item
              name="password"
              rules={[{ required: true, message: t('auth.validation.passwordRequired') }]}
            >
              <Input.Password
                prefix={<LockOutlined />}
                placeholder={t('auth.password')}
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
                {t('auth.signIn')}
              </Button>
            </Form.Item>

            <div style={{ textAlign: 'center' }}>
              <Link onClick={() => setSetupMode(true)}>
                {t('auth.firstTime')}
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
            <Title level={5}>{t('auth.initialSetup')}</Title>
            <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
              {t('auth.createFirstAdmin')}
            </Text>

            <Form.Item
              name="username"
              rules={[
                { required: true, message: t('auth.validation.usernameRequired') },
                { min: 3, message: t('auth.validation.minUsername') },
              ]}
            >
              <Input
                prefix={<UserOutlined />}
                placeholder={t('auth.username')}
                size="large"
              />
            </Form.Item>

            <Form.Item
              name="email"
              rules={[
                { required: true, message: t('auth.validation.emailRequired') },
                { type: 'email', message: t('auth.validation.emailInvalid') },
              ]}
            >
              <Input
                prefix={<UserOutlined />}
                placeholder={t('auth.email')}
                size="large"
              />
            </Form.Item>

            <Form.Item
              name="password"
              rules={[
                { required: true, message: t('auth.validation.passwordRequired') },
                { min: 8, message: t('auth.validation.minPassword') },
              ]}
            >
              <Input.Password
                prefix={<LockOutlined />}
                placeholder={t('auth.password')}
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
                {t('auth.createAdminAccount')}
              </Button>
            </Form.Item>

            <div style={{ textAlign: 'center' }}>
              <Link onClick={() => setSetupMode(false)}>
                {t('auth.backToLogin')}
              </Link>
            </div>
          </Form>
        )}
      </Card>
    </div>
  );
};
