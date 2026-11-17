import { useRef } from 'react';
import { Input, Modal } from 'antd';
import type { InputRef } from 'antd';

interface PlanRejectModalProps {
  open: boolean;
  reason: string;
  loading: boolean;
  onReasonChange: (reason: string) => void;
  onCancel: () => void;
  onSubmit: () => void;
}

export function PlanRejectModal({
  open,
  reason,
  loading,
  onReasonChange,
  onCancel,
  onSubmit,
}: PlanRejectModalProps) {
  const inputRef = useRef<InputRef>(null);

  return (
    <Modal
      className="plan-reject-modal"
      open={open}
      centered
      width={520}
      title="暂不保存这个方案？"
      okText="提交反馈"
      cancelText="返回方案"
      confirmLoading={loading}
      okButtonProps={{ disabled: !reason.trim() }}
      onOk={onSubmit}
      onCancel={onCancel}
      afterOpenChange={(visible) => {
        if (visible) inputRef.current?.focus({ cursor: 'end' });
      }}
    >
      <p className="plan-reject-modal__description" id="plan-reject-description">
        告诉我哪里需要调整，我会根据你的反馈继续完善方案。
      </p>
      <label className="plan-reject-modal__label" htmlFor="plan-reject-reason">
        调整意见
      </label>
      <Input.TextArea
        ref={inputRef}
        id="plan-reject-reason"
        aria-describedby="plan-reject-description"
        value={reason}
        autoSize={{ minRows: 4, maxRows: 6 }}
        maxLength={200}
        placeholder="例如：被保险人性别有误，或希望降低预算、调整保障。"
        onChange={(event) => onReasonChange(event.target.value)}
      />
      <div className="plan-reject-modal__meta">
        <span>提交后，当前方案不会保存</span>
        <span aria-label={`已输入 ${reason.length} 字，最多 200 字`}>
          {reason.length} / 200
        </span>
      </div>
    </Modal>
  );
}
