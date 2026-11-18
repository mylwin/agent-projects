import { LockOutlined, MailOutlined, UserOutlined } from '@ant-design/icons';
import { Alert, Form, Input, Modal, Tabs } from 'antd';
import { useState } from 'react';

import { login, register } from './api';
import type { AuthSession } from './types';

type AuthMode = 'login' | 'register';

interface AuthModalProps {
  open: boolean;
  onCancel: () => void;
  onSuccess: (session: AuthSession) => void;
}

interface AuthFormValues {
  username: string;
  email: string;
  password: string;
}

export function AuthModal({ open, onCancel, onSuccess }: AuthModalProps) {
  const [mode, setMode] = useState<AuthMode>('login');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function switchMode(next: AuthMode) {
    setMode(next);
    setError(null);
  }

  async function submit(values: AuthFormValues) {
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const session =
        mode === 'login'
          ? await login(values.username, values.password)
          : await register(values.username, values.email, values.password);
      onSuccess(session);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '操作失败，请稍后重试');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      title={null}
      footer={null}
      width={420}
      onCancel={onCancel}
      afterClose={() => {
        setMode('login');
        setError(null);
      }}
      destroyOnHidden
      centered
    >
      <div className="auth-modal__header">
        <h2>欢迎来到安心保</h2>
        <p>登录后可使用智能顾问服务</p>
      </div>
      <Tabs
        activeKey={mode}
        onChange={(key) => switchMode(key as AuthMode)}
        items={[
          { key: 'login', label: '登录' },
          { key: 'register', label: '注册' },
        ]}
      />
      {error ? (
        <Alert className="auth-modal__alert" type="error" showIcon message={error} />
      ) : null}
      <Form<AuthFormValues>
        key={mode}
        layout="vertical"
        onFinish={submit}
        requiredMark={false}
      >
        <Form.Item
          label={mode === 'login' ? '用户名 / 邮箱' : '用户名'}
          name="username"
          rules={
            mode === 'login'
              ? [{ required: true, message: '请输入用户名或邮箱' }]
              : [
                  { required: true, message: '请输入用户名' },
                  { min: 3, max: 20, message: '用户名需要 3-20 个字符' },
                ]
          }
        >
          <Input prefix={<UserOutlined />} size="large" autoComplete="username" />
        </Form.Item>
        {mode === 'register' ? (
          <Form.Item
            label="邮箱"
            name="email"
            rules={[
              { required: true, message: '请输入邮箱' },
              { type: 'email', message: '请输入有效的邮箱地址' },
            ]}
          >
            <Input prefix={<MailOutlined />} size="large" autoComplete="email" />
          </Form.Item>
        ) : null}
        <Form.Item
          label="密码"
          name="password"
          rules={[
            { required: true, message: '请输入密码' },
            { min: 6, max: 128, message: '密码需要 6-128 个字符' },
          ]}
        >
          <Input.Password
            prefix={<LockOutlined />}
            size="large"
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
          />
        </Form.Item>
        <button className="auth-submit" type="submit" disabled={submitting}>
          {submitting ? '提交中...' : mode === 'login' ? '登录' : '注册'}
        </button>
      </Form>
    </Modal>
  );
}
