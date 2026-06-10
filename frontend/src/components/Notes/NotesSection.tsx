import { useState } from 'react';
import {
  Card,
  Button,
  Input,
  Skeleton,
  Empty,
  Popconfirm,
  message,
  Tag,
} from 'antd';
import { DeleteOutlined, EditOutlined, CheckOutlined, CloseOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { listNotes, createNote, updateNote, deleteNote } from '../../api/notes';
import { useAuth } from '../../context/AuthContext';
import type { NoteResponse } from '../../types';

function NoteItem({
  note,
  candidateId,
  isOwn,
  isAdmin,
}: {
  note: NoteResponse;
  candidateId: string;
  isOwn: boolean;
  isAdmin: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(note.text);
  const queryClient = useQueryClient();

  const updateMutation = useMutation({
    mutationFn: (text: string) => updateNote(candidateId, note.id, text),
    onSuccess: () => {
      message.success('Note updated');
      queryClient.invalidateQueries({ queryKey: ['candidate', candidateId, 'notes'] });
      setEditing(false);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteNote(candidateId, note.id),
    onSuccess: () => {
      message.success('Note deleted');
      queryClient.invalidateQueries({ queryKey: ['candidate', candidateId, 'notes'] });
    },
  });

  const wasEdited =
    new Date(note.updated_at).getTime() - new Date(note.created_at).getTime() > 1000;
  const canDelete = isOwn || isAdmin;

  return (
    <Card size="small" type="inner">
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          marginBottom: 8,
          flexWrap: 'wrap',
          gap: 8,
        }}
      >
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          {isOwn && <Tag color="blue">You</Tag>}
          <span style={{ fontSize: 12, color: '#a1a1bb' }}>
            {new Date(note.created_at).toLocaleString()}
            {wasEdited && (
              <span style={{ marginLeft: 6, color: '#64648a' }}>(edited)</span>
            )}
          </span>
        </div>
        {!editing && (
          <div style={{ display: 'flex', gap: 4 }}>
            {isOwn && (
              <Button
                size="small"
                type="text"
                icon={<EditOutlined />}
                onClick={() => {
                  setDraft(note.text);
                  setEditing(true);
                }}
              />
            )}
            {canDelete && (
              <Popconfirm
                title="Delete note"
                description="Are you sure?"
                onConfirm={() => deleteMutation.mutate()}
                okText="Yes"
                cancelText="No"
              >
                <Button
                  size="small"
                  type="text"
                  danger
                  icon={<DeleteOutlined />}
                  loading={deleteMutation.isPending}
                />
              </Popconfirm>
            )}
          </div>
        )}
      </div>

      {editing ? (
        <div>
          <Input.TextArea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={3}
            style={{ marginBottom: 8 }}
          />
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <Button
              size="small"
              icon={<CloseOutlined />}
              onClick={() => setEditing(false)}
            >
              Cancel
            </Button>
            <Button
              size="small"
              type="primary"
              icon={<CheckOutlined />}
              loading={updateMutation.isPending}
              disabled={!draft.trim() || draft === note.text}
              onClick={() => updateMutation.mutate(draft)}
            >
              Save
            </Button>
          </div>
        </div>
      ) : (
        <p style={{ margin: 0, color: '#ededf5', whiteSpace: 'pre-wrap' }}>{note.text}</p>
      )}
    </Card>
  );
}

export default function NotesSection({ candidateId }: { candidateId: string }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [text, setText] = useState('');

  const { data: notes = [], isLoading } = useQuery({
    queryKey: ['candidate', candidateId, 'notes'],
    queryFn: () => listNotes(candidateId),
  });

  const createMutation = useMutation({
    mutationFn: (body: string) => createNote(candidateId, body),
    onSuccess: () => {
      message.success('Note added');
      queryClient.invalidateQueries({ queryKey: ['candidate', candidateId, 'notes'] });
      setText('');
    },
  });

  const handleSubmit = () => {
    const trimmed = text.trim();
    if (!trimmed) return;
    createMutation.mutate(trimmed);
  };

  const isAdmin = user?.role === 'admin';

  return (
    <Card title="Notes" style={{ marginBottom: 16 }}>
      <div style={{ marginBottom: 16 }}>
        <Input.TextArea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={3}
          placeholder="Add a note..."
          style={{ marginBottom: 8 }}
        />
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <Button
            type="primary"
            onClick={handleSubmit}
            loading={createMutation.isPending}
            disabled={!text.trim()}
          >
            Add Note
          </Button>
        </div>
      </div>

      {isLoading ? (
        <Skeleton active paragraph={{ rows: 3 }} />
      ) : notes.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No notes yet" />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {notes.map((note) => (
            <NoteItem
              key={note.id}
              note={note}
              candidateId={candidateId}
              isOwn={user?.id === note.author_id}
              isAdmin={isAdmin}
            />
          ))}
        </div>
      )}
    </Card>
  );
}
