1. Does my project handle closing positions? How does that work?
2. How are we handling multiple portfolios running in parallel?
3. Make sure that we batch and share all the market requests and that we extract all the markets from all the events data that we get
4. I think we need to look at refactoring the orchestrator and the strategy controllers... we'll see how that goes

=====
Current state:
- in a clunky way you can make some positions and it will track how they go over time
- you can make multiple portfolios
- when you make a strategy you have to be careful about how we are getting new markets that is not automated
- but when you run markets at the beginning you can find new opportunities and then they are constantly updated throughout the day
- it works i just want to refactor it so that it is easier to add new strategies
- not sure how the event filtering/market filtering workqs but the core infra is there
- it can definitely be used for some basic feed forward testing
- if u just manually clean all the trading positions it should work without the batching
- you would have to load the data every time you want to make a new portolfio the two tasks left to ensure it's ready for basic testing are:
-- IF YOU READ NOTNING ELSE THIS IS WHAT IS LEFT FOR BASIC TESTING:
--- DAILY FLOW DOCUMENT NEEDS TO BE CONCRETE WITH RUNBOOK.MD
--- MAKE SURE THAT WE CAN FILTER IN MEMORY WITH ONE DAILY BIG EVENT UPDATE
--- MAKE SURE THAT THE ORCHESTRATOR REFACTOR WORKS (I THINK THERE IS SOMETHING DODGY WITH THE STRATEGY TYPE)
--- MAKE SURE THAT THE CLOSING POSITION WORKS BUT LIKE ONE BASIC FLOW DOES ACTUALLY WORK 
---- WE CAN HACK AROUND BY LOADING UP A NEW SET OF EVENTS (CURRENTLY IT'S FUCKED BY IS_FILTERED, WE NEED TO ADD IN MEMORY) AND THEN RUNNING EVERYTHING AND PRICE UPDATER WORKS