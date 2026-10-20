# AI behavior and navigation
## When to use
- Enemy, NPC and companion decision-making, perception, navigation, crowds, squad tactics and AI debugging tools.
- Not for: encounter layout → `level-design`; combat tuning → `combat-design`; animation of AI characters → `animation`.
## Inputs
- Archetype behavior spec (states, perception ranges, tells, difficulty knobs), navigation requirements (agent sizes, jump/climb links), max active AI count, AI tick budget.
## Method
1. Write the behavior as states and transitions with entry and exit conditions before choosing the tool (behavior tree, state tree, utility, GOAP).
2. Separate perception (what the AI knows), decision (what it wants) and execution (move, attack, animate).
3. Expose difficulty knobs as data: reaction time, accuracy, aggression, perception range.
4. Navigation: agent radius/height per archetype, nav links for jumps and doors, dynamic obstacle handling, streaming of nav data.
5. Budget: AI LOD (lower tick rate and simpler logic far from the player), time-sliced queries, cap concurrent attackers (token system).
## Checks
- AI debugger or visual logger used to verify perception and decisions in each state; recordings attached to the report.
- No stuck or oscillating agents on the critical path; agents recover when the target is unreachable.
- AI cost at max active count within budget.
## Pitfalls
- Perfect information AI (reads player position without perception) that feels unfair.
- Behavior trees that poll expensive services every tick; decisions made inside animation code.
- Nav mesh not rebuilt or not streamed with the level, leaving agents stranded.
## Engine notes
- Unreal: Behavior Trees with Blackboard, StateTree, Environment Query System (EQS), AI Perception, Smart Objects, Mass for crowds, Navigation System with Nav Link Proxies; Gameplay Debugger (apostrophe key) and Visual Logger.
- Unity: AI Navigation package (NavMesh), Unity Behavior package for behavior graphs, or custom state machines.
- Godot: NavigationServer3D, NavigationAgent3D, NavigationLink3D; behavior trees via add-ons (for example LimboAI).
