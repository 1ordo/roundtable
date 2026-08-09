/* Packs the extension into a zip a store will accept.
 *
 * There is no bundler on purpose: the extension is plain files, so the
 * build is a copy and a zip. That keeps what runs in the browser identical
 * to what is in the repository, which matters for something that reads
 * pages you are signed into. */
const { execSync } = require('node:child_process')
const fs = require('node:fs')
const path = require('node:path')

const SHIP = [
  'manifest.json', 'background.js', 'content.js', 'sites.js', 'queue.js',
  'services.js',
  'options.html', 'options.js', 'popup.html', 'popup.js',
  'import.html', 'import.js', 'ui.css',
  'icon16.png', 'icon48.png', 'icon128.png',
]

const version = JSON.parse(fs.readFileSync('manifest.json', 'utf8')).version
const out = path.join('dist', `roundtable-extension-${version}.zip`)

const missing = SHIP.filter((f) => !fs.existsSync(f))
if (missing.length) {
  console.error('missing files, refusing to build:', missing.join(', '))
  process.exit(1)
}

// A test file or a stray key shipping to a store is the kind of mistake
// that is obvious afterwards, so the list above is explicit rather than a
// directory scan with exclusions.
fs.rmSync('dist', { recursive: true, force: true })
fs.mkdirSync('dist', { recursive: true })
execSync(`zip -q -j "${out}" ${SHIP.map((f) => `"${f}"`).join(' ')}`)

const size = (fs.statSync(out).size / 1024).toFixed(0)
console.log(`${out}  ${size} KB  ${SHIP.length} files`)
