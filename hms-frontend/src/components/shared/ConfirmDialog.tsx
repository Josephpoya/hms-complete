import React from 'react';
import { Modal, Button, Alert } from '../ui';

interface Props {
  isOpen:    boolean;
  onClose:   () => void;
  onConfirm: () => void;
  title:     string;
  message:   React.ReactNode;
  variant?:  'danger' | 'warning';
  confirmLabel?: string;
  loading?:  boolean;
}

export function ConfirmDialog({
  isOpen, onClose, onConfirm, title, message,
  variant = 'danger', confirmLabel = 'Confirm', loading,
}: Props) {
  return (
    <Modal isOpen={isOpen} onClose={onClose} title={title} size="sm">
      <Alert variant={variant === 'danger' ? 'error' : 'warning'}>
        {message}
      </Alert>
      <div className="flex justify-end gap-2 mt-5">
        <Button variant="secondary" onClick={onClose} disabled={loading}>Cancel</Button>
        <Button
          variant={variant === 'danger' ? 'danger' : 'primary'}
          onClick={onConfirm}
          isLoading={loading}
        >
          {confirmLabel}
        </Button>
      </div>
    </Modal>
  );
}
