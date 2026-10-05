import { isApiError } from '../../api/errors';
import { describeError } from '../../components/data/describeError';

export interface FormErrors {
  /** Messages for individual fields, from the server's validation details. */
  fields: Record<string, string>;
  /** A message for the whole form (wrong credentials, lockout, network, …). */
  form: string | null;
}

/** Turns a failed auth/team request into form messages. Server messages are user-facing. */
export function toFormErrors(error: unknown): FormErrors {
  if (!error) return { fields: {}, form: null };
  if (!isApiError(error)) return { fields: {}, form: describeError(error).message };

  const fields: Record<string, string> = {};
  for (const detail of error.details) {
    if (detail.field && !fields[detail.field]) fields[detail.field] = detail.message;
  }
  if (error.field && !fields[error.field]) fields[error.field] = error.message;

  switch (error.code) {
    case 'invalid_credentials':
    case 'too_many_attempts':
    case 'email_taken':
    case 'registration_closed':
    case 'last_owner':
    case 'forbidden':
      return { fields, form: error.code === 'email_taken' ? null : error.message };
    case 'invalid_request':
      return {
        fields,
        form: Object.keys(fields).length ? null : 'Check the form and try again.',
      };
    default: {
      const { title, message } = describeError(error);
      return { fields, form: `${title}. ${message}` };
    }
  }
}
