// Independent browser-side expression of the public stable ledger URL contract.
const { createHash } = require('node:crypto');
const token = value => encodeURIComponent(value).replace(/[!'()*]/g, value => '%' + value.charCodeAt(0).toString(16).toUpperCase());
const evidenceURL = (kind, id) => (kind === 'entity' ? '/research/data/' :
  '/research/data/' + (kind === 'source' ? 'sources' : 'assertions') + '/'
    + createHash('sha256').update(id, 'utf8').digest('hex')[0] + '/') + '#' + token(kind + '-' + id);
module.exports = { evidenceURL, token };
