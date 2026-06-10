import {
  Form,
  Input,
  InputNumber,
  Select,
  Button,
  Card,
} from 'antd';
import { PlusOutlined, MinusCircleOutlined } from '@ant-design/icons';
import type { CandidateData } from '../../types';

const { TextArea } = Input;

interface StepReviewProps {
  initialData: CandidateData;
  onSave: (data: CandidateData) => void;
  isSaving: boolean;
}

const seniorityOptions = [
  { value: 'junior', label: 'Junior' },
  { value: 'mid', label: 'Mid' },
  { value: 'senior', label: 'Senior' },
  { value: 'lead', label: 'Lead' },
];

export default function StepReview({ initialData, onSave, isSaving }: StepReviewProps) {
  const [form] = Form.useForm();

  const handleFinish = (values: CandidateData) => {
    onSave(values);
  };

  return (
    <Form
      form={form}
      layout="vertical"
      initialValues={initialData}
      onFinish={handleFinish}
      style={{ maxHeight: '60vh', overflowY: 'auto', paddingRight: 8 }}
    >
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <Form.Item
          name="name"
          label="Name"
          rules={[{ required: true, message: 'Name is required' }]}
        >
          <Input placeholder="Full name" />
        </Form.Item>

        <Form.Item
          name="email"
          label="Email"
          rules={[{ type: 'email', message: 'Invalid email format' }]}
        >
          <Input placeholder="email@example.com" />
        </Form.Item>

        <Form.Item name="phone" label="Phone">
          <Input placeholder="Phone number" />
        </Form.Item>

        <Form.Item name="location" label="Location">
          <Input placeholder="City, Country" />
        </Form.Item>

        <Form.Item name="years_experience" label="Years of Experience">
          <InputNumber min={0} max={50} style={{ width: '100%' }} />
        </Form.Item>

        <Form.Item name="seniority" label="Seniority">
          <Select options={seniorityOptions} placeholder="Select seniority" allowClear />
        </Form.Item>
      </div>

      <Form.Item name="skills" label="Skills">
        <Select
          mode="tags"
          placeholder="Add skills"
          tokenSeparators={[',']}
          style={{ width: '100%' }}
        />
      </Form.Item>

      <Form.Item name="summary" label="Summary">
        <TextArea rows={4} placeholder="Professional summary" />
      </Form.Item>

      <Card title="Education" size="small" style={{ marginBottom: 16 }}>
        <Form.List name="education">
          {(fields, { add, remove }) => (
            <>
              {fields.map(({ key, name, ...restField }) => (
                <div
                  key={key}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr 100px 32px',
                    gap: 8,
                    marginBottom: 8,
                    alignItems: 'start',
                  }}
                >
                  <Form.Item
                    {...restField}
                    name={[name, 'institution']}
                    rules={[{ required: true, message: 'Institution required' }]}
                    style={{ marginBottom: 0 }}
                  >
                    <Input placeholder="Institution" />
                  </Form.Item>
                  <Form.Item
                    {...restField}
                    name={[name, 'degree']}
                    style={{ marginBottom: 0 }}
                  >
                    <Input placeholder="Degree" />
                  </Form.Item>
                  <Form.Item
                    {...restField}
                    name={[name, 'year']}
                    style={{ marginBottom: 0 }}
                  >
                    <InputNumber
                      placeholder="Year"
                      min={1950}
                      max={2030}
                      style={{ width: '100%' }}
                    />
                  </Form.Item>
                  <Button
                    type="text"
                    danger
                    icon={<MinusCircleOutlined />}
                    onClick={() => remove(name)}
                    style={{ marginTop: 4 }}
                  />
                </div>
              ))}
              <Button
                type="dashed"
                onClick={() => add()}
                icon={<PlusOutlined />}
                style={{ width: '100%' }}
              >
                Add Education
              </Button>
            </>
          )}
        </Form.List>
      </Card>

      <div style={{ textAlign: 'right', marginTop: 24 }}>
        <Button type="primary" htmlType="submit" loading={isSaving}>
          Save Candidate
        </Button>
      </div>
    </Form>
  );
}
