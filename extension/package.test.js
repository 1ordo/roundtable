/* The shipped files, checked as files rather than as behaviour.
 *
 * This exists because of a bug that every other test was blind to. A comment
 * in background.js contained a Chrome match pattern, and that pattern's own
 * `*` followed by `/` closed the block comment early, leaving the rest of
 * the function as loose syntax. It had been papered over with a zero-width
 * space wedged between the two characters, which is invisible in every
 * editor and survives no copy, no reformat and no transfer. On this machine
 * the file parsed; loaded into Chrome it was a syntax error on line 91, and
 * the whole worker failed to start.
 *
 * So: nothing ships with an invisible character in it, and every file that
 * ships is parsed by the engine rather than trusted. The behavioural tests
 * import these modules, which would also fail on a syntax error, but only
 * for the two files they happen to import.
 */
const test = require('node:test')
const assert = require('node:assert')
const fs = require('node:fs')
const { execFileSync } = require('node:child_process')

/** The files build.js actually packs, read from build.js so they cannot drift. */
function shipped() {
  const source = fs.readFileSync('./build.js', 'utf8')
  const block = source.slice(source.indexOf('const SHIP = ['), source.indexOf(']', source.indexOf('const SHIP = [')))
  return [...block.matchAll(/'([^']+)'/g)].map((m) => m[1])
}

test('every file the build packs exists', () => {
  for (const file of shipped()) {
    assert.ok(fs.existsSync(file), `${file} is in the ship list but not on disk`)
  }
})

test('every shipped script is parsed by the engine, not just imported by a test', () => {
  for (const file of shipped().filter((f) => f.endsWith('.js'))) {
    assert.doesNotThrow(
      () => execFileSync(process.execPath, ['--check', file], { stdio: 'pipe' }),
      `${file} does not parse`,
    )
  }
})

/* Characters that are invisible in an editor and change how a file parses,
   or that a copy will silently drop. A zero-width space holding a comment
   together is the specific case that got us. */
const INVISIBLE = {
  '​': 'zero-width space',
  '‌': 'zero-width non-joiner',
  '‍': 'zero-width joiner',
  '﻿': 'byte order mark',
  ' ': 'non-breaking space',
  '⁠': 'word joiner',
  ' ': 'narrow non-breaking space',
}

test('nothing ships with an invisible character in it', () => {
  const found = []
  for (const file of shipped().filter((f) => /\.(js|html|css|json)$/.test(f))) {
    const lines = fs.readFileSync(file, 'utf8').split('\n')
    lines.forEach((line, index) => {
      for (const [character, name] of Object.entries(INVISIBLE)) {
        if (line.includes(character)) found.push(`${file}:${index + 1} contains a ${name}`)
      }
    })
  }
  assert.deepEqual(found, [], found.join('\n'))
})

test('no block comment is closed early by its own contents', () => {
  /* The failure mode directly: a match pattern, a glob or a regex written
     inside a block comment can contain the closing sequence. Stripping the
     comments and re-parsing would catch it, but the engine check above
     already does; this names the cause so the next person does not have to
     work it out from "missing catch or finally". */
  for (const file of shipped().filter((f) => f.endsWith('.js'))) {
    const source = fs.readFileSync(file, 'utf8')
    const lines = source.split('\n')
    lines.forEach((line, index) => {
      const trimmed = line.trim()
      // A continuation line inside a block comment, holding a stray closer
      // that is not at the end of the line, is the shape of the bug.
      if (!trimmed.startsWith('*') && !trimmed.startsWith('/*')) return
      const closer = line.indexOf('*/')
      if (closer === -1) return
      assert.ok(
        line.slice(closer + 2).trim() === '',
        `${file}:${index + 1} closes a block comment mid-line, which is almost ` +
          `always a pattern written inside one: ${trimmed.slice(0, 70)}`,
      )
    })
  }
})
