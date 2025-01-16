def execute_block(self) -> bool:
        """
        Executes the block with test-first approach and retry logic.
        Always generates tests first, then implements solution with retries.
        """
        try:
            print("Generating tests first...")
            self.agent.generate_tests(
                self.block.test_specification, 
                self.block.test_data_generation,
                self.block.function_name
            )

            max_retries = self.config['agents']['programming']['max_retries']
            for attempt in range(max_retries):
                print(f"\nAttempt {attempt + 1}/{max_retries} to implement solution...")
                
                print("Executing task...")
                self.agent.execute_task(
                    self.block.task_description,
                    self.block.function_name
                )

                print("Running tests...")
                if self.run_tests():
                    print("Tests passed successfully.")
                    return True
                else:
                    print("Tests failed.")
                    print("Test Results:")
                    print(self.get_test_results())
                    if attempt < max_retries - 1:
                        print("Retrying with a new implementation...")
                    else:
                        print("Maximum retry attempts reached. Giving up.")
                        return False

        except Exception as e:
            print(f"An error occurred during block execution: {e}")
            return False

    def run_tests(self) -> bool:
        """
        Runs the tests using pytest framework.
        Shows all test failures instead of stopping at the first one.
        """
        try:
            result = subprocess.run(
                ['pytest', 'tests/test_new_block.py', '-v', '--disable-warnings'],
                capture_output=True,
                text=True,
                cwd=self.project_dir
            )
            self.test_results = result.stdout + "\n" + result.stderr
            print("Test Results:")
            print(self.test_results)
            return result.returncode == 0
        except Exception as e:
            self.test_results = str(e)
            print(f"Error running tests: {e}")
            return False

    def get_test_results(self) -> str:
        return self.test_results