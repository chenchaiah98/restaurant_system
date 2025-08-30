const path = require("path");
const express = require("express");
const db = require("./db");
const app = express();
const PORT = process.env.PORT || 3000;

app.use(express.json());
app.use(express.static(path.join(__dirname, "public")));

// Get all restaurants
app.get("/api/restaurants", async (req, res) => {
  try {
    const rows = await db.all("SELECT * FROM restaurants ORDER BY id DESC");
    res.json(rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Get a single restaurant
app.get("/api/restaurants/:id", async (req, res) => {
  try {
    const row = await db.get("SELECT * FROM restaurants WHERE id = ?", [
      req.params.id,
    ]);
    if (!row) return res.status(404).json({ error: "Not found" });
    res.json(row);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Create
app.post("/api/restaurants", async (req, res) => {
  try {
    const { name, address } = req.body;
    if (!name) return res.status(400).json({ error: "name is required" });
    const result = await db.run(
      "INSERT INTO restaurants (name, address) VALUES (?, ?)",
      [name, address || null]
    );
    const restaurant = await db.get("SELECT * FROM restaurants WHERE id = ?", [
      result.lastID,
    ]);
    res.status(201).json(restaurant);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Update
app.put("/api/restaurants/:id", async (req, res) => {
  try {
    const { name, address } = req.body;
    const { id } = req.params;
    const info = await db.run(
      "UPDATE restaurants SET name = ?, address = ? WHERE id = ?",
      [name, address, id]
    );
    if (info.changes === 0) return res.status(404).json({ error: "Not found" });
    const updated = await db.get("SELECT * FROM restaurants WHERE id = ?", [
      id,
    ]);
    res.json(updated);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Delete
app.delete("/api/restaurants/:id", async (req, res) => {
  try {
    const { id } = req.params;
    const info = await db.run("DELETE FROM restaurants WHERE id = ?", [id]);
    if (info.changes === 0) return res.status(404).json({ error: "Not found" });
    res.status(204).end();
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.listen(PORT, () =>
  console.log(`Server listening on http://localhost:${PORT}`)
);
