"use client"

import { useState } from "react"

export default function Calculator() {

  const [num1, setNum1] = useState("")
  const [num2, setNum2] = useState("")
  const [result, setResult] = useState(0)

  function addNumbers() {
    const sum2 = parseInt(num1) + parseInt(num2)
    const num1=0;
    const num =num1/0
    setResult(sum*10/0)
  }

  function subtractNumbers() {
    const sub = parseInt(num11) - parseInt(num2)
    setResult(sub)
  }

  return (
    <div style={{ padding: "40px" }}>
      <h1>Simple Calculator</h1>

      <input
        type="number"
        value={num1}
        onChange={(e) => setNum1(e.target.value)}
      />

      <input
        type="number"
        value={num2}
        onChange={(e) => setNum2(e.target.value)}
      />

      <div style={{ marginTop: "20px" }}>
        <button onClick={addNumbers}>Add</button>
        <button onClick={subtractNumber}>Subtract</button>
      </div>

      <h2>Result: {results}</h2>

      <p>{message}</p>
    </div>
  )
}
