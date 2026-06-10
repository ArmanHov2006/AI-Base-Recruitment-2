import { useState } from 'react';
import { Upload, Button, Progress, message } from 'antd';
import { InboxOutlined } from '@ant-design/icons';
import type { UploadFile } from 'antd';

const { Dragger } = Upload;

interface StepUploadProps {
  onUploadComplete: (files: File[]) => void;
  isUploading: boolean;
  multiple?: boolean;
  uploadProgress?: { done: number; total: number } | null;
}

const MAX_FILE_SIZE = 10 * 1024 * 1024;

function validateFile(file: File): boolean {
  if (file.size > MAX_FILE_SIZE) {
    message.error(`${file.name}: file size must be less than 10 MB`);
    return false;
  }
  const isValidType =
    file.type === 'application/pdf' ||
    file.type === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
  if (!isValidType) {
    message.error(`${file.name}: only PDF and DOCX files are accepted`);
    return false;
  }
  return true;
}

export default function StepUpload({ onUploadComplete, isUploading, multiple = false, uploadProgress }: StepUploadProps) {
  const [fileList, setFileList] = useState<UploadFile[]>([]);

  const handleBeforeUpload = (file: File) => {
    if (!validateFile(file)) return false;

    const entry: UploadFile = {
      uid: crypto.randomUUID(),
      name: file.name,
      status: 'done',
      originFileObj: file as unknown as UploadFile['originFileObj'],
    };

    setFileList((prev) => (multiple ? [...prev, entry] : [entry]));
    return false;
  };

  const handleRemove = (file: UploadFile) => {
    setFileList((prev) => prev.filter((f) => f.uid !== file.uid));
  };

  const handleSubmit = () => {
    if (fileList.length === 0) {
      message.error('Please select at least one file');
      return;
    }
    const files = fileList
      .map((f) => f.originFileObj as unknown as File)
      .filter(Boolean);
    onUploadComplete(files);
  };

  const count = fileList.length;
  const buttonLabel = uploadProgress
    ? `Uploading ${uploadProgress.done}/${uploadProgress.total}…`
    : isUploading
    ? 'Uploading...'
    : multiple && count > 1
    ? `Upload ${count} Resumes`
    : 'Upload Resume';

  return (
    <div>
      <Dragger
        className="upload-dropzone"
        name="file"
        fileList={fileList}
        beforeUpload={handleBeforeUpload}
        onRemove={handleRemove}
        accept=".pdf,.docx"
        multiple={multiple}
        maxCount={multiple ? undefined : 1}
        disabled={isUploading}
      >
        <p className="ant-upload-drag-icon">
          <InboxOutlined />
        </p>
        <p className="ant-upload-text">
          {multiple ? 'Click or drag resumes to upload' : 'Click or drag resume to upload'}
        </p>
        <p className="ant-upload-hint">
          {multiple
            ? 'Supports multiple PDF and DOCX files up to 10 MB each'
            : 'Supports PDF and DOCX files up to 10 MB'}
        </p>
      </Dragger>

      {uploadProgress && (
        <Progress
          percent={Math.round((uploadProgress.done / uploadProgress.total) * 100)}
          status="active"
          style={{ marginTop: 16 }}
        />
      )}

      <div style={{ marginTop: 16, textAlign: 'right' }}>
        <Button
          type="primary"
          onClick={handleSubmit}
          loading={isUploading}
          disabled={count === 0}
        >
          {buttonLabel}
        </Button>
      </div>
    </div>
  );
}
