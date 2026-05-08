// Reference discriminated-union error helper for aspergillus consumers.
//
// Aspergillus L3 rules enforce SHAPE, not import. Consumers may use
// this helper, build their own `AspError`-shaped union, or bring an
// existing convention. The fields below are the minimum the rules
// recognize.
//
// Usage:
//   import { aspError } from '@afdudley/aspergillus/errors';
//
//   /** @typedef {import('@afdudley/aspergillus/errors').AspError<'NotFound', { id: string }>} NotFoundError */
//
//   export const notFound = (id) =>
//     aspError('NotFound', `user ${id} not found`, { id });

/**
 * @template {string} TTag
 * @template TData
 * @typedef {{
 *   readonly _tag: TTag,
 *   readonly message: string,
 *   readonly data?: TData,
 *   readonly cause?: unknown,
 * }} AspError
 */

/**
 * Construct an AspError. Plain object; no prototype chain, no
 * `instanceof` semantics. `_tag` is a literal type that drives
 * exhaustive switch checking on the consumer side.
 *
 * @template {string} TTag
 * @template TData
 * @param {TTag} tag
 * @param {string} message
 * @param {TData} [data]
 * @param {unknown} [cause]
 * @returns {AspError<TTag, TData>}
 */
export const aspError = (tag, message, data, cause) => ({
  _tag: tag,
  message,
  data,
  cause,
});
