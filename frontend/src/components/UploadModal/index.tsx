import { useState } from 'react';
import { Modal, Steps, message } from 'antd';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import StepUpload from './StepUpload';
import StepParsing from './StepParsing';
import StepReview from './StepReview';
import { uploadFile } from '../../api/files';
import { parseResume } from '../../api/parser';
import { createCandidate } from '../../api/candidates';
import type { CandidateData } from '../../types';

interface UploadModalProps {
  open: boolean;
  onClose: () => void;
}

type Step = 'upload' | 'parsing' | 'review';

export default function UploadModal({ open, onClose }: UploadModalProps) {
  const [currentStep, setCurrentStep] = useState<Step>('upload');
  const [fileId, setFileId] = useState<string | null>(null);
  const [parsedData, setParsedData] = useState<CandidateData | null>(null);
  const [parseError, setParseError] = useState<Error | null>(null);

  const queryClient = useQueryClient();

  const uploadMutation = useMutation({
    mutationFn: uploadFile,
    onSuccess: (data) => {
      setFileId(data.file_id);
      setCurrentStep('parsing');
      parseMutation.mutate(data.file_id);
    },
  });

  const parseMutation = useMutation({
    mutationFn: parseResume,
    onSuccess: (data) => {
      setParsedData(data);
      setParseError(null);
      setCurrentStep('review');
    },
    onError: (error: Error) => {
      setParseError(error);
    },
  });

  const createMutation = useMutation({
    mutationFn: createCandidate,
    onSuccess: () => {
      message.success('Candidate saved successfully');
      queryClient.invalidateQueries({ queryKey: ['candidates'] });
      handleClose();
    },
  });

  const handleClose = () => {
    setCurrentStep('upload');
    setFileId(null);
    setParsedData(null);
    setParseError(null);
    onClose();
  };

  const handleUploadComplete = (files: File[]) => {
    uploadMutation.mutate(files[0]);
  };

  const handleRetryParse = () => {
    if (fileId) {
      setParseError(null);
      parseMutation.mutate(fileId);
    }
  };

  const handleSave = (data: CandidateData) => {
    if (!fileId) return;
    createMutation.mutate({
      ...data,
      file_id: fileId,
    });
  };

  const stepIndex = currentStep === 'upload' ? 0 : currentStep === 'parsing' ? 1 : 2;

  return (
    <Modal
      title="Upload Resume"
      open={open}
      onCancel={handleClose}
      footer={null}
      width={640}
      destroyOnHidden
    >
      <Steps
        current={stepIndex}
        items={[
          { title: 'Upload' },
          { title: 'Parsing' },
          { title: 'Review & Save' },
        ]}
        style={{ marginBottom: 24 }}
      />

      {currentStep === 'upload' && (
        <StepUpload
          onUploadComplete={handleUploadComplete}
          isUploading={uploadMutation.isPending}
        />
      )}

      {currentStep === 'parsing' && (
        <StepParsing
          isParsing={parseMutation.isPending}
          error={parseError}
          onRetry={handleRetryParse}
        />
      )}

      {currentStep === 'review' && parsedData && (
        <StepReview
          initialData={parsedData}
          onSave={handleSave}
          isSaving={createMutation.isPending}
        />
      )}
    </Modal>
  );
}
