Sync workouts from Hevy API to a local sqlite database, and then use that to do things like
1: generate charts using Streamlit
2: develop progressive overloads (using an LLM to analyse training data)

It also currently creates a CSV version of the data. The original thinking was to make this data file available to a Gemini app for using with Gemini. That logic isn't currently implemented.