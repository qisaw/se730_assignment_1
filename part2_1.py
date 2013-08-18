
import sys, os, signal, time, threading
from multiprocessing import Semaphore


# These functions are to be scheduled and run in separate real processes.
def low_func(proc):
    pid = os.getpid() # who am I?
    print('Low priority:', pid, '- just about to request resource')
    controller_write.write('{0}:request\n'.format(pid))
    response = proc.read.readline()
    print('Low priority:', pid, '- got resource')
                           
    sum = 0
    for i in range(100000000):
        sum += i

    controller_write.write('{0}:release\n'.format(pid))
    print('Low priority:', pid, '- released resource')
        
    for i in range(100000000):
        sum += i

    print('Low priority:', pid, '- finished')


def mid_func(proc):
    for i in range(1, 11):
        print('Mid priority:', i)
        time.sleep(0.5)

def high_func(proc):
    pid = os.getpid() # who am I?
    print('High priority:', pid, '- just about to request resource')
    controller_write.write('{0}:request\n'.format(pid))
    response = proc.read.readline()
    print('High priority:', pid, '- got resource')
    controller_write.write('{0}:release\n'.format(pid))
    print('High priority:', pid, '- released resource')

    
#===============================================================================
class SimpleProcess():
    def __init__(self, priority, function):
        self.pid = None
        self.priority = priority
        self.func = function
        # Set up the pipe which will later be used to send replies to the process
        # from the controller.
        r, w = os.pipe()
        self.read = os.fdopen(r)
        self.write = os.fdopen(w, mode='w', buffering=1)

    # Creates the new process for this to run in when 'run' is first called.
    def run(self):
        self.pid = os.fork() # the child is the process
        
        if self.pid: # in the parent
            self.read.close()
            processes[self.pid] = self
            
        else: # in the child
            self.write.close()
            self.func(self)
            os._exit(0) # what would happen if this wasn't here?

#===============================================================================
# This is in control of the single resource.
# Only one process at a time is allowed access to the resource.
r, w = os.pipe()
controller_read = os.fdopen(r)
controller_write = os.fdopen(w, mode='w', buffering=1)

class Controller():

    def run(self):
        owner = None
        queue = []
        priotiyInherited = False
        previousPriority = 0;
        previousProcess=None;
        numOfTimesRequested=0;
        print(numOfTimesRequested)

        while True:
            input_string = controller_read.readline()
            if input_string.strip() == 'terminate':
                return
            pid, message = input_string.strip().split(':')
            pid = int(pid)
            # possible race condition on line below
            requesting_process = processes[pid]
            if message == 'request':
                if not owner: # no current owner
                    owner = requesting_process
                    owner.write.write('reply\n')
                    numOfTimesRequested=1;
                    #print(numOfTimesRequested)
                else: # currently owned
                    '''now we must have a way of checking if the requesting process is the same as the process that first
                    took hold of the resource'''
                    if requesting_process==owner:
                        numOfTimesRequested+=1
                        #print(numOfTimesRequested)
                    
                    '''make sure that the old priority value of the process is restored when the high priority 
                    process has ended'''
                    if(owner.priority < requesting_process.priority):
                        priotiyInherited = True
                        previousPriority = owner.priority
                        previousProcess = owner
                        owner.priority=requesting_process.priority
                        #reschedule the current process with the higher priority
                        scheduler.remove_process(owner)
                        scheduler.add_process(owner)
                        '''set a flag first to say that a priotiry has been changed
                        store the prioriy value and the owner of the process
                        in this case it is owner'''
                    scheduler.remove_process(requesting_process)
                    #queue.append(requesting_process)
                    self.insert_to_queue(requesting_process, queue)
            elif message == 'release' and owner == requesting_process:
                '''decrement the value of numOfTimesRequested'''
                numOfTimesRequested-=1
                if(numOfTimesRequested ==0):
                #print(numOfTimesRequested)
                    '''if a priority has been inherited, reset that priority and set the 
                    priotiy inherited flag to false'''
                    if priotiyInherited:
                        previousProcess.priority=previousPriority
                        priotiyInherited = False
                    
                
                    # the first in the queue gets it
                    if len(queue) < 1:
                        owner = None
                    else:
                        owner = queue.pop(0)
                        scheduler.add_process(owner)
                        owner.write.write('reply\n')
                        numOfTimesRequested+=1
                    #print(numOfTimesRequested)
            print('owner pid:', owner.pid if owner else None)
    def insert_to_queue(self, process,queue):
        index = len(queue)
        for i in range(len(queue)-1,-1,-1):
            if (queue[i].priority<process.priority):
                index=i
        queue.insert(index,process)
                
    

#===============================================================================
# The dummy scheduler.
# Every second it selects the next process to run.
class Scheduler():

    def __init__(self):
        self.ready_list = []
        self.last_run = None;\
        self.semafore=Semaphore(1);

    # Add a process to the run list
    def add_process(self, process):
        #set the index as the last element of the list at the begining
        #RACE condition here!!
        '''
        Say a process with priority 1 comes into the ready_list with 5 elements
        The ready_list priorities are as shown
        ready_list_priorities={10,8,8,6,4}
        the index=len(self.ready_list) line executes
        and gets the value 5. This means index =5
        then say before the next line is executed, another process  is added to the ready_list, its priority is 3
        then ready_list_priorities={10,8,8,6,4,3}
        but index is still 5 so new process will be inserted here rather than at the end of the list
        so ready_list_priorities={10,8,8,6,4,1,3}
        this is incorrect
        we must lock this method and only allow one process to access it at a time
        maybe with a semaphore
        '''
        self.semafore.acquire()
        index=len(self.ready_list)
        #find the first priority that is less than the priority of the process
        for i in range (len(self.ready_list)-1,-1,-1):
            if self.ready_list[i].priority<process.priority:
                index = i
        #add the item there
        self.ready_list.insert(index, process)
        self.semafore.release()
        return


    def remove_process(self, process):
        #do more shit to ensure that all things remain the way they are
        self.ready_list.remove(process)

    # Selects the process with the best priority.
    # If more than one have the same priority these are selected in round-robin fashion.
    def select_process(self):
        #return none if the process list is empty
        if len(self.ready_list)==0:
            return None
        
        #otherwise check to see if the lastrun process process is the same as the current running process
        if self.last_run == self.ready_list[0]:
            #make sure the list doesnt contain only one process
            if len(self.ready_list)>1:
                
                #check to see that here are no more processes with the same or higher priority level
                #because the ready_list is already sorted, we only need to check the next element and check that it is not
                #of equal or higher priority
                if(self.last_run.priority<=self.ready_list[1].priority):
                    #if it is, remove this process from the readylist and put it back in
                    #This has the effect of placing it behind all the processes with the same priority level as this process
                    self.remove_process(self.last_run)
                    self.add_process(self.last_run)
                
        #return the process that is at the head of the queue and move it to the tail of the queue
        self.last_run = self.ready_list[0]
        return self.ready_list[0]

    # Suspends the currently running process by sending it a STOP signal.
    @staticmethod
    def suspend(process):
        os.kill(process.pid, signal.SIGSTOP)

    # Resumes a process by sending it a CONT signal.
    @staticmethod
    def resume(process):
        if process.pid: # if the process has a pid it has started
            os.kill(process.pid, signal.SIGCONT)
        else:
            process.run()
    
    def run(self):
        current_process = None
        while True:
            #print('length of ready_list:', len(self.ready_list))
            next_process = self.select_process()
            if next_process == None: # no more processes
                controller_write.write('terminate\n')
                sys.exit()
            if next_process != current_process:
                if current_process:
                    self.suspend(current_process)
                current_process = next_process
                self.resume(current_process)
            time.sleep(1)
            # need to remove dead processes from the list
            try:
                current_process_finished = (
                    os.waitpid(current_process.pid, os.WNOHANG) != (0, 0)
                )
            except ChildProcessError:
                current_process_finished = True
            if current_process_finished:
                print('remove process', current_process.pid, 'from ready list')
                self.remove_process(current_process)
                current_process = None
        
#===============================================================================

controller = Controller()
scheduler = Scheduler()
processes = {}

# Priorities range from 1 to 10
low_process = SimpleProcess(1, low_func)
scheduler.add_process(low_process)

threading.Thread(target=scheduler.run).start()

time.sleep(0.5) # give low_process a chance to get going
low_process1 = SimpleProcess(1, low_func)
scheduler.add_process(low_process1)
time.sleep(0.5)
high_process = SimpleProcess(10, high_func)
scheduler.add_process(high_process)

mid_process = SimpleProcess(5, mid_func)
scheduler.add_process(mid_process)

controller.run()

print('finished')

