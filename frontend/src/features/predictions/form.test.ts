// @vitest-environment node
import { describe, expect, it } from 'vitest';

import openapiRaw from '../../../openapi.json?raw';
import {
  EMPTY_FORM,
  mapServerErrors,
  PREDICTION_LIMITS,
  toPredictionRequest,
  validatePrediction,
  type PredictionFormValues,
} from './form';

const valid: PredictionFormValues = {
  ...EMPTY_FORM,
  title: 'A title',
  category: 'Sports',
  country: 'IN',
  duration_sec: '93.5',
  channel_subscriber_count: '10',
  channel_video_count: '2',
  channel_view_count: '300',
};

describe('PREDICTION_LIMITS', () => {
  it('match the PredictionRequest limits in the OpenAPI contract', () => {
    const spec = JSON.parse(openapiRaw) as {
      components: {
        schemas: { PredictionRequest: { properties: Record<string, Record<string, unknown>> } };
      };
    };
    const p = spec.components.schemas.PredictionRequest.properties;
    expect(PREDICTION_LIMITS).toEqual({
      title: p.title!.maxLength,
      description: p.description!.maxLength,
      channel_title: p.channel_title!.maxLength,
      tags: p.tags!.maxItems,
      tag: (p.tags!.items as { maxLength: number }).maxLength,
      duration_sec: p.duration_sec!.maximum,
      channel_subscriber_count: p.channel_subscriber_count!.maximum,
      channel_video_count: p.channel_video_count!.maximum,
      channel_view_count: p.channel_view_count!.maximum,
    });
  });

  it('cover every field of the form, and the form covers exactly the schema', () => {
    const spec = JSON.parse(openapiRaw) as {
      components: { schemas: { PredictionRequest: { properties: Record<string, unknown> } } };
    };
    expect(Object.keys(EMPTY_FORM).sort()).toEqual(
      Object.keys(spec.components.schemas.PredictionRequest.properties).sort(),
    );
  });
});

describe('toPredictionRequest', () => {
  it('builds the request body: numbers parsed, tags split and trimmed', () => {
    expect(toPredictionRequest({ ...valid, tags: ' a, b ,, c ' })).toEqual({
      title: 'A title',
      description: '',
      tags: ['a', 'b', 'c'],
      channel_title: '',
      category: 'Sports',
      country: 'IN',
      duration_sec: 93.5,
      channel_subscriber_count: 10,
      channel_video_count: 2,
      channel_view_count: 300,
    });
  });
});

describe('validatePrediction', () => {
  it('accepts a complete form', () => {
    expect(validatePrediction(valid)).toEqual({});
  });

  it('requires the required fields', () => {
    expect(Object.keys(validatePrediction(EMPTY_FORM)).sort()).toEqual(
      [
        'category',
        'channel_subscriber_count',
        'channel_video_count',
        'channel_view_count',
        'country',
        'duration_sec',
        'title',
      ].sort(),
    );
  });

  it.each([
    ['channel_video_count', '2.5', 'Enter a whole number.'],
    ['channel_subscriber_count', '-1', 'Must be 0 or more.'],
    ['channel_view_count', '1e14', 'Must be at most 10,000,000,000,000.'],
    ['duration_sec', 'abc', 'Enter a number.'],
  ] as const)('%s = %s -> %s', (field, value, message) => {
    expect(validatePrediction({ ...valid, [field]: value })[field]).toBe(message);
  });

  it('checks text and tag limits', () => {
    expect(validatePrediction({ ...valid, title: 'x'.repeat(201) }).title).toMatch(/200/);
    expect(validatePrediction({ ...valid, tags: Array(51).fill('t').join(',') }).tags).toMatch(
      /50/,
    );
    expect(validatePrediction({ ...valid, tags: 'x'.repeat(101) }).tags).toMatch(/100/);
  });
});

describe('mapServerErrors', () => {
  it('maps backend detail fields onto form fields', () => {
    expect(
      mapServerErrors([
        { field: 'country', message: 'bad country' },
        { field: 'tags.3', message: 'tag too long' },
        { field: 'unknown_field', message: 'other' },
        { field: null, message: 'general' },
      ]),
    ).toEqual({
      fields: { country: 'bad country', tags: 'tag too long' },
      form: ['other', 'general'],
    });
  });
});
