import apiClient from './client';
import type { NoteResponse } from '../types';

export async function listNotes(candidateId: string): Promise<NoteResponse[]> {
  const response = await apiClient.get<NoteResponse[]>(`/candidates/${candidateId}/notes`);
  return response.data;
}

export async function createNote(candidateId: string, text: string): Promise<NoteResponse> {
  const response = await apiClient.post<NoteResponse>(`/candidates/${candidateId}/notes`, {
    text,
  });
  return response.data;
}

export async function updateNote(
  candidateId: string,
  noteId: string,
  text: string,
): Promise<NoteResponse> {
  const response = await apiClient.patch<NoteResponse>(
    `/candidates/${candidateId}/notes/${noteId}`,
    { text },
  );
  return response.data;
}

export async function deleteNote(candidateId: string, noteId: string): Promise<void> {
  await apiClient.delete(`/candidates/${candidateId}/notes/${noteId}`);
}
