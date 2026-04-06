from firewall.gateway_wrapper import guarded_call

class Agent:
    def __init__(self, name):
        self.name = name
        self.last_output = None

    def run(self, prompt, drift_score=0.0):
        result = guarded_call(prompt, drift_score=drift_score, agent=self.name)

        if not result["blocked"]:
            self.last_output = result["response"]

        return result


class Coordinator:
    def __init__(self):
        self.agents = {}

    def add_agent(self, name):
        self.agents[name] = Agent(name)

    def run(self, name, prompt, drift_score=0.0):
        agent = self.agents[name]
        result = agent.run(prompt, drift_score)

        return {
            "agent": name,
            "output": result["response"],
            "blocked": result["blocked"],
            "reason": result["reason"],
        }
