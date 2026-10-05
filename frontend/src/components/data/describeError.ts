import { isApiError } from '../../api/errors';

interface DescribedError {
  title: string;
  message: string;
  requestId: string | null;
  canRetry: boolean;
}

/** User-facing description of an error. Never exposes stack traces or internals. */
export function describeError(error: unknown): DescribedError {
  if (!isApiError(error)) {
    return {
      title: 'Something went wrong',
      message: 'This section could not be displayed.',
      requestId: null,
      canRetry: true,
    };
  }
  const requestId = error.requestId;
  switch (error.code) {
    case 'invalid_filter':
    case 'invalid_parameter':
    case 'invalid_request':
      // Backend validation messages are written for users (e.g. the available date range).
      return {
        title: "These filters can't be applied",
        message: error.message,
        requestId,
        canRetry: false,
      };
    case 'not_found':
      return {
        title: 'Not found',
        message: 'The requested item does not exist.',
        requestId,
        canRetry: false,
      };
    case 'forbidden':
      return {
        title: 'Access denied',
        message: 'Your role does not allow this. Ask a workspace owner or admin.',
        requestId,
        canRetry: false,
      };
    case 'not_authenticated':
      return {
        title: 'Your session has ended',
        message: 'Sign in again to continue.',
        requestId,
        canRetry: false,
      };
    case 'network_error':
      return {
        title: "Can't reach the API",
        message: 'Check that the backend is running, then try again.',
        requestId,
        canRetry: true,
      };
    case 'timeout':
    case 'query_timeout':
      return {
        title: 'The request took too long',
        message: 'Try a shorter date range or fewer filters.',
        requestId,
        canRetry: true,
      };
    case 'database_unavailable':
    case 'database_busy':
      return {
        title: 'Data is temporarily unavailable',
        message: 'The data service is busy or offline. Please try again shortly.',
        requestId,
        canRetry: true,
      };
    default:
      return {
        title: 'Something went wrong',
        message: 'The data could not be loaded.',
        requestId,
        canRetry: true,
      };
  }
}
