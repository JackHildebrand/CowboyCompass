import { useState } from 'react'
import './App.css'

const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000/api/schedules'
const TERM_OPTIONS = [
  { value: 'fall-2026', label: 'Fall 2026' },
  { value: 'spring-2027', label: 'Spring 2027' },
]
const classesForDay = (schedule, day) =>
  schedule.classes[day.toLowerCase()] || schedule.classes[day] || []
const crnsForSchedule = (schedule) => {
  const sections = new Map()
  Object.values(schedule.classes).flat().forEach((item) => {
    if (item.crn && !sections.has(item.course)) sections.set(item.course, item.crn)
  })
  return [...sections]
}
const visibleDays = (schedule) => WEEKDAYS.filter((day) => !['Saturday', 'Sunday'].includes(day) || classesForDay(schedule, day).length > 0)
const courseColor = (course) => [...course].reduce((total, character) => total + character.charCodeAt(0), 0) % 6
const rmpSearchUrl = (professor) => `https://www.ratemyprofessors.com/search/professors?q=${encodeURIComponent(professor)}`
const scoreColor = (score, schedules) => {
  const scores = schedules.map((schedule) => schedule.score)
  const lowest = Math.min(...scores)
  const highest = Math.max(...scores)
  const quality = highest === lowest ? 1 : (highest - score) / (highest - lowest)
  const hue = Math.round(quality * 120)
  return `hsl(${hue} 58% 38%)`
}
const formatCourse = (value) => {
  const compact = value.trim().toUpperCase().replace(/\s+/g, '')
  const match = compact.match(/^([A-Z]+)(.+)$/)
  return match ? `${match[1]} ${match[2]}` : compact
}

function App() {
  const [term, setTerm] = useState('fall-2026')
  const [courseInput, setCourseInput] = useState('')
  const [courses, setCourses] = useState([])
  const [schedules, setSchedules] = useState([])
  const [resultCount, setResultCount] = useState(0)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [copiedCrn, setCopiedCrn] = useState('')

  function addCourse(event) {
    event.preventDefault()
    const formatted = formatCourse(courseInput)
    if (!formatted || courses.some((course) => course.replace(/\s/g, '') === formatted.replace(/\s/g, ''))) return
    setCourses([...courses, formatted])
    setCourseInput('')
    setSchedules([])
    setResultCount(0)
    setError('')
  }

  function removeCourse(course) {
    setCourses(courses.filter((item) => item !== course))
    setSchedules([])
    setResultCount(0)
    setError('')
  }

  async function findSchedules() {
    if (courses.length === 0) {
      setError('Add at least one course before searching.')
      return
    }
    setIsLoading(true)
    setError('')
    try {
      const response = await fetch(API_URL, {
        method: 'POST',
        cache: 'no-store',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ courses, term }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.error || 'The schedule search failed.')
      setSchedules(data.schedules)
      setResultCount(data.conflictFreeSchedules)
    } catch (requestError) {
      setError(`${requestError.message} Start the Python API with python3 api.py, then try again.`)
    } finally {
      setIsLoading(false)
    }
  }

  async function copyCrn(crn) {
    if (!navigator.clipboard) return
    await navigator.clipboard.writeText(String(crn))
    setCopiedCrn(String(crn))
    window.setTimeout(() => setCopiedCrn(''), 1600)
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="Cowboy Compass home">
          <span className="brand-mark" aria-hidden="true">
            <img src="/cowboy-compass-logo-white.png" alt="" />
          </span>
          <span className="brand-name">Cowboy Compass</span>
        </a>
      </header>

      <section className="workspace-grid">
        <aside className="control-panel">
          <div className="eyebrow">Schedule builder</div>
          <h1>Build a week that works.</h1>
          <p className="intro">Add the courses you need and compare conflict-free sections in one place.</p>

          <label className="term-select-label" htmlFor="term-select">Term</label>
          <div className="term-select-wrap">
            <select id="term-select" className="term-select" value={term} onChange={(event) => { setTerm(event.target.value); setSchedules([]); setResultCount(0); setError(''); setCopiedCrn('') }} disabled={isLoading}>
              {TERM_OPTIONS.map((option) => <option key={option.value} value={option.value} disabled={option.disabled}>{option.label}</option>)}
            </select>
            <span className="term-select-arrow" aria-hidden="true" />
          </div>

          <form className="course-form" onSubmit={addCourse}>
            <label htmlFor="course-input">Requested courses</label>
            <div className="input-row">
              <input id="course-input" value={courseInput} onChange={(event) => setCourseInput(event.target.value)} placeholder="e.g. MATH 2144" autoComplete="off" />
              <button type="submit" className="add-button" aria-label="Add course">+</button>
            </div>
          </form>

          <div className="course-list" aria-live="polite">
            {courses.map((course) => (
              <div className="course-chip" key={course}>
                <span>{course}</span>
                <button type="button" onClick={() => removeCourse(course)} aria-label={`Remove ${course}`}>×</button>
              </div>
            ))}
          </div>

          <button className="primary-button" type="button" onClick={findSchedules} disabled={isLoading}>
            {isLoading ? 'Finding schedules…' : 'Find schedules'} <span aria-hidden="true">→</span>
          </button>
          {error && <p className="error-message" role="alert">{error}</p>}

          <div className="scoring-note">
            <span className="note-dot" aria-hidden="true" />
            <div><strong>How ranking works</strong><p>Fewer class days are strongly preferred. One fewer day outweighs up to 24 hours of extra weekly gaps; among schedules with the same number of days, shorter gaps rank higher.</p></div>
          </div>
        </aside>

        <section className="results-panel" aria-live="polite">
          <div className="results-header">
            <div><div className="eyebrow">Results</div><h2>Top schedules</h2></div>
            <div className="result-count"><span>{resultCount}</span> conflict-free options</div>
          </div>

          <div className="schedule-list">
            {schedules.length === 0 ? (
              <div className="empty-state">
                <div className="empty-icon" aria-hidden="true">⌘</div>
                <h3>Ready when you are</h3>
                <p>Choose your courses, then select Find schedules to build your week.</p>
              </div>
            ) : schedules.map((schedule, index) => (
              <article className={`schedule-card ${index === 0 ? 'featured' : ''}`} key={`${index}-${schedule.score}-${schedule.gap}-${schedule.days}`}>
                <div className="schedule-summary">
                  <div className="score-badge" style={{ color: scoreColor(schedule.score, schedules) }} aria-label={`Score ${schedule.score}`}>{schedule.score}</div>
                  <div className="schedule-heading"><h3>{index === 0 ? 'Best fit' : `Option ${index + 1}`}</h3><p>{schedule.days} class days · {schedule.gap} minutes between classes</p></div>
                  <div className="crn-list" aria-label="Course registration numbers">
                    {crnsForSchedule(schedule).map(([course, crn]) => (
                      <button className="crn-button" type="button" key={`${course}-${crn}`} onClick={() => copyCrn(crn)} aria-label={`Copy CRN ${crn} for ${course}`}>
                        <span>{course} · {crn}</span><span className="copy-label">{copiedCrn === String(crn) ? 'Copied' : 'Copy'}</span>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="calendar" style={{ '--calendar-days': visibleDays(schedule).length }}>
                  {visibleDays(schedule).map((day) => (
                    <div className="day-column" key={day}>
                      <div className="day-name">{day.slice(0, 3)}</div>
                      {classesForDay(schedule, day).length === 0 ? <div className="no-class">—</div> : classesForDay(schedule, day).map((item, meetingIndex) => (
                        <div className={`class-block course-color-${courseColor(item.course)}`} key={`${day}-${item.crn}-${meetingIndex}`}>
                          <time>{item.time}</time><strong>{item.course}</strong><span>{item.title}</span><span className="class-meta">{item.room}</span>{item.professor === 'TBA' ? <span className="class-meta">TBA</span> : <a className="class-meta professor-link" href={rmpSearchUrl(item.professor)} target="_blank" rel="noreferrer">{item.professor} ↗</a>}<span className="class-meta">{item.meetingType} · CRN {item.crn}</span>{item.startDate && item.endDate && <span className="class-meta">{item.startDate}–{item.endDate}</span>}
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              </article>
            ))}
          </div>
        </section>
      </section>
    </main>
  )
}

export default App
